#####################################################
# Creator: Anubhab Ghosh
# July 2024
#####################################################
# Import necessary libraries
import os

import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(SCRIPT_DIR))

import argparse  # noqa: E402
import json  # noqa: E402
import pickle as pkl  # noqa: E402

# import matplotlib.pyplot as plt
import torch  # noqa: E402
from parse import parse  # noqa: E402
from src.danse import DANSE, train_danse  # , test_danse  # noqa: E402

from utils.utils import (  # noqa: E402
    NDArrayEncoder,
    Series_Dataset,
    check_if_dir_or_file_exists,
    create_splits_file_name,
    get_dataloaders,
    load_saved_dataset,
    load_splits_file,
    obtain_tr_val_test_idx,
) 
# Import the parameters
from config.parameters_opt import get_H_DANSE, get_parameters  # noqa: E402

# from utils.plot_functions import plot_measurement_data, plot_measurement_data_axes, plot_state_trajectory, plot_state_trajectory_axes
# Import estimator model and functions



def main():

    parser = argparse.ArgumentParser(
        usage="Train DANSE using trajectories of SSMs \n"
        "python3.8 main_danse.py --mode [train/test] --model_type [gru/lstm/rnn] --dataset_mode [LinearSSM/LorenzSSM] \n"
        "--datafile [fullpath to datafile] --splits [fullpath to splits file]",
        description="Input a string indicating the mode of the script \n"
        "train - training and testing is done, test-only evlaution is carried out"
    )
    parser.add_argument("--mode", help="Enter the desired mode", type=str)
    parser.add_argument(
        "--rnn_model_type", help="Enter the desired model (rnn/lstm/gru)", type=str
    )
    parser.add_argument(
        "--dataset_type", help="Enter the type of dataset (pfixed/vars/all)", type=str
    )
    parser.add_argument(
        "--datafile", help="Enter the full path to the dataset", type=str
    )
    parser.add_argument("--splits", help="Enter full path to splits file", type=str)

    args = parser.parse_args()
    mode = args.mode
    model_type = args.rnn_model_type
    datafile = args.datafile
    dataset_type = args.dataset_type
    #datafolder = "".join(
    #    datafile.split("/")[i] + "/" for i in range(len(datafile.split("/")) - 1)
    #)
    splits_file = args.splits

    print("datafile: {}".format(datafile))
    print(datafile.split("/")[-1])
    # Dataset parameters obtained from the 'datafile' variable
    (
        data_string,
        n_states,
        n_obs,
        _,
        measurement_fn_type,
        T,
        N_samples,
        sigma_e2_dB,
        smnr_dB,
    ) = parse(
        "{}_m_{:d}_n_{:d}_{}_{}_data_T_{:d}_N_{:d}_sigmae2_{:f}dB_smnr_{:f}dB.pkl",
        datafile.split("/")[-1],
    )

    ngpu = 1  # Comment this out if you want to run on cpu and the next line just set device to "cpu"
    device = torch.device(
        "cuda:0" if (torch.cuda.is_available() and ngpu > 0) else "cpu"
    )
    print("Device Used:{}".format(device))

    ssm_parameters_dict, est_parameters_dict = get_parameters(
        n_states=n_states,
        n_obs=n_obs,
        device=device,
        measurment_fn_type=measurement_fn_type,
    )

    batch_size = est_parameters_dict["danse"]["batch_size"]  # Set the batch size
    estimator_options = est_parameters_dict[
        "danse"
    ]  # Get the options for the estimator

    if not os.path.isfile(datafile):
        print(
            "Dataset is not present, run 'generate_data.py / run_generate_data.sh' to create the dataset"
        )
        # plot_trajectories(Z_pM, ncols=1, nrows=10)
    else:
        print("Dataset already present!")
        Z_XY = load_saved_dataset(filename=datafile)

    Z_XY_dataset = Series_Dataset(Z_XY_dict=Z_XY)
    ssm_model = Z_XY["ssm_model"]
    estimator_options["C_w"] = (
        ssm_model.Cw
    )  # Get the covariance matrix of the measurement noise from the model information
    estimator_options["H"] = get_H_DANSE(
        type_=dataset_type, n_states=n_states, n_obs=n_obs
    )  # Get the sensing matrix from the model info

    print(estimator_options["H"])
    if not os.path.isfile(splits_file):
        tr_indices, val_indices, test_indices = obtain_tr_val_test_idx(
            dataset=Z_XY_dataset, tr_to_test_split=0.9, tr_to_val_split=0.833
        )
        print(len(tr_indices), len(val_indices), len(test_indices))
        splits = {}
        splits["train"] = tr_indices
        splits["val"] = val_indices
        splits["test"] = test_indices
        splits_file_name = create_splits_file_name(
            dataset_filename=datafile, splits_filename=splits_file
        )

        print("Creating split file at:{}".format(splits_file_name))
        with open(splits_file_name, "wb") as handle:
            pkl.dump(splits, handle, protocol=pkl.HIGHEST_PROTOCOL)
    else:
        print("Loading the splits file from {}".format(splits_file))
        splits = load_splits_file(splits_filename=splits_file)
        tr_indices, val_indices, test_indices = (
            splits["train"],
            splits["val"],
            splits["test"],
        )

    train_loader, val_loader, test_loader = get_dataloaders(
        dataset=Z_XY_dataset,
        batch_size=batch_size,
        tr_indices=tr_indices,
        val_indices=val_indices,
        test_indices=test_indices,
    )

    print(
        "No. of training, validation and testing batches: {}, {}, {}".format(
            len(train_loader), len(val_loader), len(test_loader)
        )
    )

    # ngpu = 1 # Comment this out if you want to run on cpu and the next line just set device to "cpu"
    # device = torch.device("cuda:0" if (torch.cuda.is_available() and ngpu>0) else "cpu")
    # print("Device Used:{}".format(device))

    logfile_path = "./log/"
    modelfile_path = "./models/"

    # NOTE: Currently this is hardcoded into the system
    main_exp_name = "{}_danse_opt_{}_m_{}_n_{}_T_{}_N_{}_sigmae2_{}dB_smnr_{}dB".format(
        dataset_type, model_type, n_states, n_obs, T, N_samples, sigma_e2_dB, smnr_dB
    )

    # print(params)
    tr_log_file_name = "training.log"

    flag_log_dir, flag_log_file = check_if_dir_or_file_exists(
        os.path.join(logfile_path, main_exp_name), file_name=tr_log_file_name
    )

    print("Is log-directory present:? - {}".format(flag_log_dir))
    print("Is log-file present:? - {}".format(flag_log_file))

    flag_models_dir, _ = check_if_dir_or_file_exists(
        os.path.join(modelfile_path, main_exp_name), file_name=None
    )

    print("Is model-directory present:? - {}".format(flag_models_dir))
    # print("Is file present:? - {}".format(flag_file))

    tr_logfile_name_with_path = os.path.join(
        os.path.join(logfile_path, main_exp_name), tr_log_file_name
    )

    if flag_log_dir is False:
        print("Creating {}".format(os.path.join(logfile_path, main_exp_name)))
        os.makedirs(os.path.join(logfile_path, main_exp_name), exist_ok=True)

    if flag_models_dir is False:
        print("Creating {}".format(os.path.join(modelfile_path, main_exp_name)))
        os.makedirs(os.path.join(modelfile_path, main_exp_name), exist_ok=True)

    modelfile_path = os.path.join(
        modelfile_path, main_exp_name
    )  # Modify the modelfile path to add full model file

    if mode.lower() == "train":
        model_danse = DANSE(**estimator_options)
        tr_verbose = True

        # Starting model training
        tr_losses, val_losses, _, _, _ = train_danse(
            model=model_danse,
            train_loader=train_loader,
            val_loader=val_loader,
            options=estimator_options,
            nepochs=model_danse.rnn.num_epochs,
            logfile_path=tr_logfile_name_with_path,
            modelfile_path=modelfile_path,
            save_chkpoints="some",
            device=device,
            tr_verbose=tr_verbose,
        )
        # if tr_verbose == True:
        #    plot_losses(tr_losses=tr_losses, val_losses=val_losses, logscale=False)

        losses_model = {}
        losses_model["tr_losses"] = tr_losses
        losses_model["val_losses"] = val_losses

        with open(
            os.path.join(
                os.path.join(logfile_path, main_exp_name),
                "danse_{}_losses_eps{}.json".format(
                    estimator_options["rnn_type"],
                    estimator_options["rnn_params_dict"][model_type]["num_epochs"],
                ),
            ),
            "w",
        ) as f:
            f.write(json.dumps(losses_model, cls=NDArrayEncoder, indent=2))

    return None


if __name__ == "__main__":
    main()
