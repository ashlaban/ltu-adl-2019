"""
This file is the entry point of DeepDIVA.

@authors: Vinaychandran Pondenkandath , Michele Alberti
"""

import json
# Utils
import os
import sys
import traceback

# Tensor board
import tensorboardX
# SigOpt
from sigopt import Connection
# Python
from sklearn.model_selection import ParameterGrid

# DeepDIVA
import template.CL_arguments
import template.runner
from init.initializer import *
from template.setup import set_up_env, set_up_logging
from util.misc import to_capital_camel_case
from util.visualization.mean_std_plot import plot_mean_variance


########################################################################################################################
class RunMe:
    # TODO: improve doc
    """
    This file is the entry point of DeepDIVA.
    In particular depending on the args passed one can:
        -single run
        -multi run
        -optimize with SigOpt
        -optimize manually (grid)

    For details on parameters check CL_arguments.py
    """

    # Reference to the argument parser. Useful for accessing types of arguments later e.g. setup.set_up_logging()
    parser = None

    def main(self):
        args, RunMe.parser = template.CL_arguments.parse_arguments()

        if args.sig_opt is not None:
            self._run_sig_opt(args)
        elif args.hyper_param_optim is not None:
            self._run_manual_optimization(args)
        else:
            self._execute(args)

    def _run_sig_opt(self, args):
        # TODO: improve doc
        """
        This function creates a new SigOpt experiment and optimizes the selected parameters.

        Parameters:
        -----------
        :param args:
        :return:
            None
        """
        # Load parameters from file
        with open(args.sig_opt, 'r') as f:
            parameters = json.loads(f.read())
        if args.experiment_name is None:
            args.experiment_name = input("Experiment name:")

        # Client Token is currently Vinay's one
        conn = Connection(client_token="KXMUZNABYGKSXXRUEMELUYYRVRCRTRANKCPGDNNYDSGRHGUA")
        experiment = conn.experiments().create(
            name=args.experiment_name,
            parameters=parameters,
        )
        print("Created experiment: https://sigopt.com/experiment/" + experiment.id)
        for i in range(args.sig_opt_runs):
            # Get suggestion from SigOpt
            suggestion = conn.experiments(experiment.id).suggestions().create()
            params = suggestion.assignments
            for key in params:
                args.__dict__[key] = params[key]
            _, _, score = self._execute(args)
            # In case of multi-run the return type will be a list (otherwise is a single float)
            if type(score) != float:
                [conn.experiments(experiment.id).observations().create(suggestion=suggestion.id, value=item)
                 for item in score]
            else:
                conn.experiments(experiment.id).observations().create(suggestion=suggestion.id, value=score)

    def _run_manual_optimization(self, args):
        # TODO: improve doc
        """
        Run a manual optimization search with the parameters provided


        Parameters:
        -----------
        :param args:
        :return:
            None
        """
        print('Hyper Parameter Optimization mode')
        with open(args.hyper_param_optim, 'r') as f:
            hyper_param_values = json.loads(f.read())
        hyper_param_grid = ParameterGrid(hyper_param_values)
        for i, params in enumerate(hyper_param_grid):
            print('{} of {} possible parameter combinations evaluated'.format(i, len(hyper_param_grid)))
            for key in params:
                args.__dict__[key] = params[key]
            self._execute(args)

    @staticmethod
    def _execute(args):
        # TODO: improve doc
        """

        Parameters:
        -----------
        :param args:
        :return:
        """
        # Set up logging
        args.__dict__['log_dir'] = set_up_logging(parser=RunMe.parser, args_dict=args.__dict__, **args.__dict__)

        # Define Tensorboard SummaryWriter
        logging.info('Initialize Tensorboard SummaryWriter')
        writer = tensorboardX.SummaryWriter(log_dir=args.log_dir)

        # Set up execution environment
        # Specify CUDA_VISIBLE_DEVICES and seeds
        set_up_env(**args.__dict__)

        # Select with introspection which runner class should be used. Default is runner.standard.Standard
        runner_class = getattr(sys.modules["template.runner." + args.runner_class],
                               args.runner_class).__dict__[to_capital_camel_case(args.runner_class)]

        try:
            if args.multi_run is not None:
                train_scores, val_scores, test_scores = RunMe._multi_run(runner_class, writer, args)
            else:
                train_scores, val_scores, test_scores = runner_class.single_run(writer, **args.__dict__)
        except Exception as exp:
            if args.quiet:
                print('Unhandled error: {}'.format(repr(exp)))
            logging.error('Unhandled error: %s' % repr(exp))
            logging.error(traceback.format_exc())
            logging.error('Execution finished with errors :(')
            sys.exit(-1)
        finally:
            logging.shutdown()
            logging.getLogger().handlers = []
            writer.close()
            print('All done! (logged to {}'.format(args.log_dir))
            args.log_dir = None
        return train_scores, val_scores, test_scores

    @staticmethod
    def _multi_run(runner_class, writer, args):
        """
        Here multiple runs with same parameters are executed and the results averaged.
        Additionally "variance shaded plots" gets to be generated and are visible not only on FS but also on
        tensorboard under 'IMAGES'.

        Parameters:
        -----------
        :param runner_class: class
            This is necessary to know on which class should we run the experiments.  Default is runner.standard.Standard

        :param writer: Tensorboard SummaryWriter
            Responsible for writing logs in Tensorboard compatible format.

        :param args:
            Any additional arguments (especially for the runner_class)

        :return: float[n, epochs], float[n, epochs], float[n]
            Train, Val and Test results for each run (n) and epoch
        """

        # Init the scores tables which will stores the results.
        train_scores = np.zeros((args.multi_run, args.epochs))
        val_scores = np.zeros((args.multi_run, args.epochs))
        test_scores = np.zeros(args.multi_run)

        # As many times as runs
        for i in range(args.multi_run):
            logging.info('Multi-Run: {} of {}'.format(i + 1, args.multi_run))
            train_scores[i, :], val_scores[i, :], test_scores[i] = runner_class.single_run(writer,
                                                                                           run=i,
                                                                                           **args.__dict__)

            # Generate and add to tensorboard the shaded plot for train
            train_curve = plot_mean_variance(train_scores[:i + 1],
                                             suptitle='Multi-Run: Train',
                                             title='Runs: {}'.format(i + 1),
                                             xlabel='Epochs', ylabel='Accuracy',
                                             ylim=[0, 100.0])
            writer.add_image('train_curve', train_curve)
            logging.info('Generated mean-variance plot for train')

            # Generate and add to tensorboard the shaded plot for val
            val_curve = plot_mean_variance(val_scores[:i + 1],
                                           suptitle='Multi-Run: Val',
                                           title='Runs: {}'.format(i + 1),
                                           xlabel='Epochs', ylabel='Accuracy',
                                           ylim=[0, 100.0])
            writer.add_image('val_curve', val_curve)
            logging.info('Generated mean-variance plot for val')

        # Log results on disk
        np.save(os.path.join(args.log_dir, 'train_values.npy'), train_scores)
        np.save(os.path.join(args.log_dir, 'val_values.npy'), val_scores)
        logging.info('Multi-run values for test-mean:{} test-std: {}'.format(np.mean(test_scores), np.std(test_scores)))

        return train_scores, val_scores, test_scores


########################################################################################################################
if __name__ == "__main__":
    RunMe().main()