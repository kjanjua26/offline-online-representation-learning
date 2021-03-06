import numpy as np
from dqn_agent import DQNAgent
from mix_ttn_agent_online_offline import TTNAgent_online_offline_mix
import os
import time
# import matplotlib.pyplot as plt
from collections import OrderedDict
import itertools
import torch as T
import argparse
# import datetime as date
from datetime import datetime
from replay_memory import ReplayBuffer
from training3 import train_offline_online, train_online, train_offline
import training3
np_load_old = np.load
# modify the default parameters of np.load
np.load = lambda *a, **k: np_load_old(*a, allow_pickle=True)
import gym

def main(alg_type, hyper_num, data_length_num, mem_size, num_rep, offline, fqi_rep_num, num_step_ratio_mem, en,
         dirfeature, feature, num_epoch ,batch_size, replace_target_cnt,target_separate, method_sarsa, data_dir, learning_feat):

    data_lengths = [mem_size, 6000, 10000, 20000, 30000]
    data_length = data_lengths[data_length_num]

    fqi_reps = [1, 10, 50, 100, 300]
    fqi_rep = fqi_reps[fqi_rep_num]

    if feature == 'tc':
        tilecoding = 1
    else:
        tilecoding = 0

    alg = alg_type

    gamma = 0.99

    rand_seed = num_rep * 32  # 332

    num_steps = num_step_ratio_mem  # 200000

    ## normolize states
    def process_state(state, normalize=True):
        # states = np.array([state['position'], state['vel']])
        if normalize:
            if en == "Acrobot":
                states = np.array([state[0], state[1], state[2], state[3], state[4], state[5]])
                states[0] = (states[0] + 1) / (2)
                states[1] = (states[1] + 1) / (2)
                states[2] = (states[2] + 1) / (2)
                states[3] = (states[3] + 1) / (2)
                states[4] = (states[4] + (4 * np.pi)) / (2 * 4 * np.pi)
                states[5] = (states[5] + (9 * np.pi)) / (2 * 4 * np.pi)
            elif en == "LunarLander":
                states = np.array([state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7]])
                mean = [0, 0.9, 0, -0.6, 0, 0, 0, 0]
                deviation = [0.35, 0.6, 0.7, 0.6, 0.5, 0.5, 1.0, 1.0]
                states[0] = (states[0] - mean[0]) / (deviation[0])
                states[1] = (states[1] - mean[1]) / (deviation[1])
                states[2] = (states[2] - mean[2]) / (deviation[2])
                states[3] = (states[3] - mean[3]) / (deviation[3])
                states[4] = (states[4] - mean[4]) / (deviation[4])
                states[5] = (states[5] - mean[5]) / (deviation[5])

            elif en == "cartpole":
                states = np.array([state[0], state[1], state[2], state[3]])
                states[0] = states[0]
                states[1] = states[1]
                states[2] = states[2]
                states[3] = states[3]

            elif en == "Mountaincar":
                states = np.array([state[0], state[1]])
                states[0] = (states[0] + 1.2) / (0.6 + 1.2)
                states[1] = (states[1] + 0.07) / (0.07 + 0.07)

            elif en == "catcher":
                states = np.array([state['player_x'], state['player_vel'], state['fruit_x'], state['fruit_y']])
                states[0] = (states[0] - 25.5) / 26
                states[1] = states[1] / 10
                states[2] = (states[2] - 30) / 22
                states[3] = (states[3] - 18.5) / 47

        return states

    ple_rewards = {
        "positive": 1.0,
        "negative": -1.0,
        "tick": 0.0,
        "loss": -0.0,
        "win": 5.0
    }

    ## select environment
    if en == "Mountaincar":
        env = gym.make('MountainCar-v0')
        input_dim = env.observation_space.shape[0]
        num_act = 3
    elif en == "Acrobot":
        env = gym.make('Acrobot-v1')
        input_dim = env.observation_space.shape[0]
        num_act = 3
    elif en == "LunarLander":
        env = gym.make('LunarLander-v2')
        input_dim = env.observation_space.shape[0]
        num_act = 4
    elif en == "cartpole":
        env = gym.make('CartPole-v0')
        input_dim = env.observation_space.shape[0]
        num_act = 2

    env.seed(rand_seed)
    T.manual_seed(rand_seed)
    np.random.seed(rand_seed)


    # dqn:
    hyper_sets_DQN = OrderedDict([("nn_lr", np.power(10, [-3.25, -3.5, -3.75, -4.0, -4.25])),
                                  ("eps_decay_steps", [10000, 20000, 40000]),
                                  ])

    ## DQN
    q_nnet_params = {"update_fqi_steps": 50000,
                     "num_actions": num_act,
                     "eps_init": 1.0,
                     "eps_final": 0.01,
                     "batch_size": 32,  # TODO try big batches
                     "replay_memory_size": mem_size,
                     "replay_init_size": 5000,
                     "update_target_net_steps": 1000
                     }

    ## TTN
    nnet_params = {"loss_features": 'semi_MSTDE',  # "next_reward_state", next_state, semi_MSTDE
                   "beta1": 0.0,
                   "beta2": 0.99,
                   "eps_init": 1.0,
                   "eps_final": 0.01,
                   "num_actions": num_act,
                   "replay_memory_size": mem_size,  # 200000 if using ER
                   "replay_init_size": 5000,
                   "batch_size": 32,
                   "fqi_reg_type": "prev",  # "l2" or "prev"
                   }
    ## TTN
    hyper_sets_lstdq = OrderedDict([("nn_lr", np.power(10, [-4.0])),  # [-2.0, -2.5, -3.0, -3.5, -4.0]
                                    ("reg_A",
                                     [10, 20, 30, 50, 70, 100, 2, 3, 5, 8, 1, 0, 0.01, 0.002, 0.0003, 0.001, 0.05]),
                                    # [0.0, -1.0, -2.0, -3.0] can also do reg towards previous weights
                                    ("eps_decay_steps", [1]),
                                    ("update_freq", [1000]),
                                    ("data_length", [data_length]),
                                    ("fqi_rep", [fqi_rep]),
                                    ])

    files_name = "Data//{}_{}".format(en, mem_size)

    if rnd:
        files_name = "Data//{}_rnd_{}".format(en, mem_size)

    if alg == 'fqi':
        log_file = files_name+str(alg)
    if alg == 'dqn':
        log_file = files_name+str(alg)

    if alg in ("fqi"):
        hyper_sets = hyper_sets_lstdq
        TTN = True
    elif alg == "dqn":
        hyper_sets = hyper_sets_DQN
        TTN = False
    #
    hyperparams_all = list(itertools.product(*list(hyper_sets.values())))
    hyperparams = hyperparams_all

    with open(log_file + ".txt", 'w') as f:
        print("Start! Seed: {}".format(rand_seed), file=f)

    times = []
    start_time = time.perf_counter()

    # num_steps = 200000
    prev_action_flag = 1
    num_repeats = num_rep  # 10
    # TTN = True

    # for hyper in hyperparams:
    # run the algorithm
    hyper = hyperparams[hyper_num]
    hyperparam_returns = []
    hyperparam_values = []
    hyperparam_episodes = []
    hyperparam_losses = []

    data = dict([('state', []), ('action', []), ('reward', []), ('nstate', []), ('naction', []), ('done', [])])


    if alg in ('lstdq', 'fqi'):
        params = OrderedDict([("nn_lr", hyper[0]),
                              ("reg_A", hyper[1]),
                              ("eps_decay_steps", hyper[2]),
                              ("update_freq", hyper[3]),
                              ("data_length", hyper[4]),
                              ("fqi_rep", hyper[5]),
                              ])
    elif alg in ("dqn"):
        params = OrderedDict([("nn_lr", hyper[0]),
                              ("eps_decay_steps", hyper[1])])



    if TTN:

        nn = TTNAgent_online_offline_mix(gamma, nnet_params=nnet_params, other_params=params,
                                             input_dims=input_dim, num_units_rep=128, dir=dir, offline=offline,
                                             num_tiling=16, num_tile=4, method_sarsa=method_sarsa,
                                             tilecoding=tilecoding, replace_target_cnt=replace_target_cnt, target_separate=target_separate)

    else:
        nn = DQNAgent(gamma, q_nnet_params, params, input_dims=input_dim)


    def generate_data():

        for rep in range(1):

            with open(log_file + ".txt", 'a') as f:
                print("new run for the current setting".format(rep), file=f)

            # saver = tf.train.Saver(keep_checkpoint_every_n_hours=2)

            # populate the replay buffer with some number of transitions
            if alg == 'dqn' or (TTN and nnet_params['replay_memory_size'] > 0):
                print("initialize buffer")
                frame_history = []
                prev_state = None
                prev_action = None
                done = 0
                state_unnormal = env.reset()
                state = process_state(state_unnormal)
                # populate the replay buffer
                while nn.memory.mem_cntr < mem_size: #nnet_params["replay_init_size"]:

                    if done:
                        state_unnormal = env.reset()
                        state = process_state(state_unnormal)

                    # get action
                    action = np.random.randint(0, num_act)

                    # add to buffer
                    if prev_state is not None:
                        if prev_action_flag == 1:
                            nn.memory.store_transition_withnewaction(prev_state, np.squeeze(prev_action), reward, state,
                                                                     np.squeeze(action), int(done))
                        else:
                            nn.memory.store_transition(prev_state, np.squeeze(prev_action), reward, state, int(done))

                    # do one step in the environment
                    new_state_unnormal, reward, done, info = env.step(np.squeeze(action))  # action is a 1x1 matrix
                    new_state = process_state(new_state_unnormal)
                    # update saved states
                    prev_state = state
                    prev_action = action
                    state = new_state

            #############################################

            prev_state = None
            prev_action = None

            run_returns = []
            run_episodes = []
            run_episode_length = []
            run_values = []
            run_losses = []

            start_run_time = time.perf_counter()
            episode_length = 0
            done = 0
            val = 0.0
            ret = 0.0
            episodes = 0
            ctr = 0
            ch = 0

            state_unnormal = env.reset()
            state = process_state(state_unnormal)
            i = 0

            for ij in range(num_steps):

                episode_length += 1
                i += 1

                if done:
                    run_episodes.append(episodes)
                    run_returns.append(ret)
                    run_episode_length.append(episode_length)

                    with open(log_file + ".txt", 'a') as f:
                        print('time:', datetime.today().strftime("%H_%M_%S"), 'return', '{}'.format(int(val)).ljust(4),
                              i,
                              len(run_returns),
                              "\t{:.2f}".format(np.mean(run_returns[-100:])), file=f)

                    if TTN:
                        print(episodes, ij, round(val, 2), round(ret, 2), round(np.mean(run_returns[-100:]), 3), np.mean(run_returns),
                              episode_length)  # nn.lin_values.data
                    else:
                        print(episodes, ij, round(val, 2), round(ret, 2), round(np.mean(run_returns[-100:]), 3), np.mean(run_returns),
                              episode_length)
                    # avg_returns.append(np.mean(all_returns[-100:]))
                    print("episode length is:", episode_length, "return is:", ret)
                    val = 0.0
                    ret = 0.0
                    i = 0
                    episodes += 1
                    episode_length = 0
                    state_unnormal = env.reset()
                    state = process_state(state_unnormal)



                ## Get action
                if TTN:
                    action = nn.choose_action(state)
                    q_values = nn.lin_values

                else:  # DQN
                    action, q_values = nn.choose_action(state)

                # run_values.append(T.mean(q_values.data, axis=1)[0].detach())

                # update parameters
                if prev_state is not None:
                    if prev_action_flag == 1:
                        if reward > 0:
                            for ii in range(1):
                                nn.memory.store_transition_withnewaction(prev_state, np.squeeze(prev_action), reward,
                                                                         state,
                                                                         np.squeeze(action), int(done))
                                ctr += 1
                        else:
                            nn.memory.store_transition_withnewaction(prev_state, np.squeeze(prev_action), reward, state,
                                                                     np.squeeze(action), int(done))
                            ctr += 1
                    else:
                        if reward > 0:
                            for ii in range(1):
                                nn.memory.store_transition(prev_state, np.squeeze(prev_action), reward, state,
                                                           int(done))
                                ctr += 1
                        else:
                            nn.memory.store_transition(prev_state, np.squeeze(prev_action), reward, state, int(done))
                            ctr += 1

                    ## stop updating
                    if TTN:
                        loss = nn.learn()
                        # if val >= 400:
                        #     ch = 1
                        # if ch == 0:
                        #     loss = nn.learn()
                        #     print("learning, ch", ch)

                    else:  # DQN
                        loss = nn.learn()

                    run_losses.append(loss.detach())

                # do one step in the environment
                new_state_unnormal, reward, done, info = env.step(np.array(action))  # action is a 1x1 matrix
                new_state = process_state(new_state_unnormal)

                # update saved states
                prev_state = state
                prev_action = action
                state = new_state  # action is a 1x1 matrix
                state_unnormal = new_state_unnormal
                reward = reward
                val += reward
                ret += (gamma ** i) * reward

            hyperparam_returns.append(run_returns)
            hyperparam_episodes.append(run_episodes)
            hyperparam_losses.append(run_losses)

            data['state'] = nn.memory.state_memory
            data['action'] = nn.memory.action_memory
            data['reward'] = nn.memory.reward_memory
            data['nstate'] = nn.memory.new_state_memory
            data['naction'] = nn.memory.new_action_memory
            data['done'] = nn.memory.terminal_memory

            np.save(files_name, data)

            print(episodes)
            print(data['state'].size(), mem_size)
            print(ctr)
            np.save(files_name+"_run_returns.npy", run_returns)
            np.save(files_name + "_run_episode_length.npy", run_episode_length)

        return files_name


    if not os.path.isfile(files_name+".npy"):
        files_name = generate_data()


    print(f"Files Name: {files_name+'.npy'}")
    return files_name+'.npy'


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    ## for data generating
    parser.add_argument('--algo', type=str, default='fqi')
    parser.add_argument('--hyper_num', type=int, default=15)
    parser.add_argument('--data_length_num', type=int, default=0)
    parser.add_argument('--mem_size', type=int, default=50000)
    parser.add_argument('--num_rep', type=int, default=1)
    parser.add_argument('--offline', type=bool, default=False)
    parser.add_argument('--fqi_rep_num', type=int, default=0)
    parser.add_argument('--num_step_ratio_mem', type=int, default=120000)
    parser.add_argument('--en', type=str, default='Mountaincar')  # set name of the environment here e.g. Mountaincar,
    parser.add_argument('--fqi_reg_type', type=str, default='prev')  # l2, prev :--> type of regularizer for fqi
    parser.add_argument('--method_sarsa', type=str, default='expected-sarsa')  # expected-sarsa, q-learning


    ## for feature learning:
    parser.add_argument('--dirfeature', type=str, default=None) #loading batch data for feature learning
    parser.add_argument('--feature', type=str, default='learned_fet')  # 'tc', 'learned_fet' :--> #type of features
    parser.add_argument('--num_epoch', type=int, default=100)
    parser.add_argument('--batch_size', type=int, default=64)
    parser.add_argument('--replace_target_cnt', type=int, default=1000)
    parser.add_argument('--target_separate', type=bool, default=True)

    parser.add_argument('--data_dir', type=str, default=None)  # direction for the batch data
    parser.add_argument('--featurepath', type=str, default=None)  # direction for the features
    parser.add_argument('--starting_state_path', type=str, default=None)  # direction for the starting_state_path
    parser.add_argument('--learning_feat', type=bool, default=False)


    ##########################################################
    ##########################################################

    parser.add_argument('--offline_online_training', type=str, default=None)  # set type of your validation: offline or online or offline_online

    ############################################################
    ############################################################
    ## for validation:
    parser.add_argument('--tr_alg_type', type=str, default='fqi')
    parser.add_argument('--tr_hyper_num', type=int, default=12) #cart =10, l2, mc=15, 13, prev - acr=13, l2
    parser.add_argument('--tr_data_length_num', type=int, default=0)
    parser.add_argument('--tr_num_rep', type=int, default=10)
    parser.add_argument('--tr_fqi_rep_num', type=int, default=0)
    parser.add_argument('--tr_num_step_ratio_mem', type=int, default=70000)
    parser.add_argument('--tr_feature', type=str, default='learned_fet')   # 'tc', 'learned_fet'
    parser.add_argument('--tr_method_sarsa', type=str, default='expected-sarsa')  # expected-sarsa, q-learning
    parser.add_argument('--tr_num_updates_pretrain', type=int, default=100)
    parser.add_argument('--tr_num_iteration', type=int, default=1)
    parser.add_argument('--tr_num_epi_per_itr', type=int, default=200)
    parser.add_argument('--tr_num_updates', type=int, default=2)
    parser.add_argument('--tr_fqi_reg_type', type=str, default='prev')  # l2, prev :--> type of regularizer for fqi
    parser.add_argument('--tr_epsilon_stop_training', type=float, default=10e-7)
    parser.add_argument('--tr_status', type=float, default=10e-7)
    parser.add_argument('--tr_offline', type=bool, default=False) # this should be False only for online setting
    parser.add_argument('--tr_initial_batch', type=bool, default=False) # this should be False only for online setting

    rnd = 0

    args = parser.parse_args()

    if args.data_dir == None:
        files_names_npy = main(args.algo, args.hyper_num, args.data_length_num, args.mem_size, args.num_rep, args.offline, args.fqi_rep_num,
         args.num_step_ratio_mem, args.en, args.dirfeature, args.feature, args.num_epoch,args.batch_size, args.replace_target_cnt, args.target_separate,
         args.method_sarsa, args.data_dir, args.learning_feat)

        args.data_dir, args.featurepath, args.starting_state_path = files_names_npy, files_names_npy, files_names_npy

        if rnd == 1:
            if args.mem_size == 10000:
                if args.en== 'Mountaincar':
                    args.data_dir = 'Data//Mountaincar_rnd_10000.npy'
                if args.en == 'Acrobot':
                    args.data_dir = 'Data//Acrobot_rnd_10000.npy'
                if args.en == 'cartpole':
                    args.data_dir = 'Data//cartpole_rnd_10000.npy'
                if args.en == 'LunarLander':
                    args.data_dir = 'Data//LunarLander_rnd_10000.npy'
            elif args.mem_size == 50000:
                if args.en== 'Mountaincar':
                    args.data_dir = 'Data//Mountaincar_rnd_50000.npy'
                if args.en == 'Acrobot':
                    args.data_dir = 'Data//Acrobot_rnd_50000.npy'
                if args.en == 'cartpole':
                    args.data_dir = 'Data//cartpole_rnd_50000.npy'
                if args.en == 'LunarLander':
                    args.data_dir = 'Data//LunarLander_rnd_50000.npy'

        if args.offline_online_training == 'offline_online':
            args.tr_offline = True
            args.tr_initial_batch = True

            train_offline_online(args.data_dir, args.starting_state_path, args.tr_alg_type, args.tr_hyper_num,
                         args.tr_data_length_num, args.mem_size, args.tr_num_rep,
                         args.tr_offline, args.tr_fqi_rep_num,
                         args.tr_num_step_ratio_mem, args.en,
                         args.tr_feature, args.tr_method_sarsa, args.tr_num_epi_per_itr,
                         args.tr_fqi_reg_type, args.tr_initial_batch, rnd, args.tr_num_updates_pretrain, args.tr_epsilon_stop_training, args.offline_online_training)


        elif args.offline_online_training == 'offline':
            args.tr_offline = True
            args.tr_initial_batch = True

            train_offline(args.data_dir, args.starting_state_path, args.tr_alg_type, args.tr_hyper_num,
                                   args.tr_data_length_num, args.mem_size, args.tr_num_rep,
                                   args.tr_offline, args.tr_fqi_rep_num,
                                   args.tr_num_step_ratio_mem, args.en,
                                   args.tr_feature, args.tr_method_sarsa, args.tr_num_epi_per_itr,
                                   args.tr_fqi_reg_type, args.tr_initial_batch, rnd, args.tr_num_updates_pretrain,
                                   args.tr_epsilon_stop_training, args.offline_online_training)

        elif args.offline_online_training == 'online':
            # args.tr_offline = False
            # args.tr_initial_batch = False
            train_online(args.data_dir, args.starting_state_path, args.tr_alg_type, args.tr_hyper_num, args.tr_data_length_num, args.mem_size, args.tr_num_rep,
                                 args.tr_offline, args.tr_fqi_rep_num,
                             args.tr_num_step_ratio_mem, args.en,
                             args.tr_feature, args.tr_method_sarsa, args.tr_num_epi_per_itr,
                             args.tr_fqi_reg_type, args.tr_initial_batch, rnd, args.offline_online_training)