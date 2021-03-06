import numpy as np
from dqn_agent import DQNAgent
from mix_ttn_agent_online_offline import TTNAgent_online_offline_mix
import os
import sys
import random
import gym
import time
from collections import OrderedDict
import itertools
import copy
import torch as T
import argparse
from datetime import datetime
from replay_memory import ReplayBuffer


def train_online(data_dir, starting_state_path,alg_type, hyper_num,
                 data_length_num, mem_size, num_rep, offline, 
                 fqi_rep_num, num_step_ratio_mem, en,
                 feature, method_sarsa,num_epi_per_itr, 
                 fqi_reg_type, initial_batch, rnd, status):

    print("online", hyper_num, en, mem_size)

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

    num_steps = num_step_ratio_mem  # 200000

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
                     "update_target_net_steps": 100
                     }

    ## TTN
    nnet_params = {"loss_features": 'next_state',  # "next_reward_state", next_state, semi_MSTDE
                   "beta1": 0.0,
                   "beta2": 0.99,
                   "eps_init": 1.0,
                   "eps_final": 0.01,
                   "num_actions": num_act,
                   "replay_memory_size": mem_size,  # 200000 if using ER
                   "replay_init_size": 5000,
                   "batch_size": 32,
                   "fqi_reg_type": fqi_reg_type,  # "l2" or "prev"
                   }
    ## TTN
    hyper_sets_lstdq = OrderedDict([("nn_lr", np.power(10, [-3.0])),  # [-2.0, -2.5, -3.0, -3.5, -4.0]
                                    ("reg_A",
                                     [10, 20, 30, 50, 70, 100, 2, 3, 5, 8, 1, 0, 0.01, 0.002, 0.0003, 0.001, 0.05]),
                                    # [0.0, -1.0, -2.0, -3.0] can also do reg towards previous weights
                                    ("eps_decay_steps", [1]),
                                    ("update_freq", [1000]),
                                    ("data_length", [data_length]),
                                    ("fqi_rep", [fqi_rep]),
                                    ])

    files_name = "Online//Training_{}_online_env_{}_mem_size_{}_date_{}_hyper_{}".format(alg_type, en, mem_size, datetime.today().strftime(
                                                                                            "%d_%m_%Y"), hyper_num
                                                                                        )
    if rnd:
        files_name = files_name+'_rnd'
    if initial_batch:
        files_name = files_name + '_initialbatch_'

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

    times = []
    start_time = time.perf_counter()

    prev_action_flag = 1
    num_repeats = num_rep  # 10

    hyper = hyperparams[hyper_num]


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



    saved_state_list_all = np.load(starting_state_path)  # np.load starting states

    hyperparam_returns = []
    hyperparam_values = []
    hyperparam_episodes = []
    hyperparam_losses = []

    hyperparam_avgreturns = []
    hyperparam_avgvalues = []
    hyperparam_avgepisodes = []
    hyperparam_avgepisodevalues = []

    hyperparam_stdreturns= []
    hyperparam_stdvalues = []
    hyperparam_stdepisodes = []
    hyperparam_stdepisodevalues = []

    hyperparam_final_avgreturns = []
    hyperparam_final_avgvalues = []
    hyperparam_final_avgepisodes = []
    hyperparam_final_avgepisodevalues = []

    hyperparam_final_stdreturns = []
    hyperparam_final_stdvalues = []
    hyperparam_final_stdepisodes = []
    hyperparam_final_stdepisodevalues = []

    for rep in range(num_repeats):

        rand_seed = rep * 32  # 332
        env.seed(rand_seed)
        T.manual_seed(rand_seed)
        np.random.seed(rand_seed)

        with open(log_file + ".txt", 'w') as f:
            print("Start! Seed: {}".format(rand_seed), file=f)

        if TTN:

            nn = TTNAgent_online_offline_mix(gamma, nnet_params=nnet_params, other_params=params,
                                             input_dims=input_dim, num_units_rep=128, dir=data_dir, offline=offline,
                                             num_tiling=16, num_tile=4, method_sarsa=method_sarsa,
                                             tilecoding=tilecoding, status=status)

        else:
            nn = DQNAgent(gamma, q_nnet_params, params, input_dims=input_dim, dir=data_dir, status = status)

        if initial_batch == False:

            if alg == 'dqn' or (TTN and nnet_params['replay_memory_size'] > 0):
                print("initialize buffer")
                frame_history = []
                prev_state = None
                prev_action = None
                done = 0
                state_unnormal = env.reset()
                state = process_state(state_unnormal)
                # populate the replay buffer
                while nn.memory.mem_cntr < nnet_params["replay_init_size"]:

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
                    prev_state = state
                    prev_action = action
                    state = new_state

        else:
            nn.memory.offline = True
            nn.memory.load_mem()


        prev_state = None
        prev_action = None

        run_returns = []
        run_vals = []
        run_episode_length = []
        run_avg_episode_values = []

        run_losses = []



        for itr in range(1):

            # # do update before running the agent
            # for j in range(num_updates_pretrain):
            #     if TTN:
            #         nn.learn_pretrain()
            #
            #     else:  # DQN
            #         loss = nn.learn()

            run_avgreturns = []
            run_avgvals = []
            run_avgepisode_length = []

            done = 0
            episodes = 0
            val = 0.0
            q_values_episode = 0
            ret = 0
            episode_length = 0
            count_10epi = 0

            env.reset()
            # game = env.unwrapped
            # env.state = saved_state_list[count_10epi]
            # state_unnormal = env.state
            # state = process_state(state_unnormal)

            # state_unnormal = env.unwrapped.state
            state_unnormal = env.reset()
            state = process_state(state_unnormal)

            start_run_time = time.perf_counter()

            i = 0

            while episodes < num_epi_per_itr + 1:
                i += 1
                if done:
                    run_returns.append(ret)
                    run_vals.append(val)
                    run_episode_length.append(episode_length)
                    run_avg_episode_values.append((q_values_episode / episode_length))

                    run_avgreturns.append(ret)
                    run_avgvals.append(val)
                    run_avgepisode_length.append(episode_length)

                    print(episodes, i, round(val, 2), ret, "number episode from 10:", count_10epi,
                          "avegar over 10 episode:", round(np.mean(run_avgreturns), 3),
                          "avegare return across last 100 episodes:", round(np.mean(run_returns[-100:]), 3),
                          "state values:", (q_values_episode / episode_length), episode_length)

                    count_10epi += 1
                    episode_length = 0
                    q_values_episode = 0
                    val = 0.0
                    ret = 0.0
                    i = 0
                    episodes += 1

                    env.reset()
                    # env.state = saved_state_list[count_10epi]
                    # state_unnormal = env.state
                    # state = process_state(state_unnormal)

                    # state_unnormal = env.unwrapped.state
                    state_unnormal = env.reset()
                    state = process_state(state_unnormal)

                    if TTN:
                        nn.load_data()
                        nn.learn_pretrain()


                # Get action
                if TTN:
                    action = nn.choose_action(state)
                    q_values = nn.lin_values

                else:  # DQN
                    action, q_values = nn.choose_action(state)

                # run_values.append(T.mean(q_values.data, axis=1)[0].detach())
                q_values_episode += T.mean(q_values.data)

                # update parameters
                if prev_state is not None:
                    # prev_state_normal = process_state(prev_state)
                    # state_normal = process_state(state)
                    if prev_action_flag == 1:
                        nn.memory.store_transition_withnewaction(prev_state, np.squeeze(prev_action), reward, state,
                                                                 np.squeeze(action), int(done))
                    else:
                        nn.memory.store_transition(prev_state, np.squeeze(prev_action), reward, state, int(done))

                    if TTN:
                        loss = nn.learn()

                    else:  # DQN
                        loss = nn.learn()

                    # run_losses.append(loss.detach())

                # do one step in the environment
                episode_length += 1
                new_state_unnormal, reward, done, info = env.step(np.array(action))  # action is a 1x1 matrix
                new_state = process_state(new_state_unnormal)

                # update saved states
                prev_state = state
                prev_action = action
                state = new_state  # action is a 1x1 matrix
                val += reward

                if reward > 100 or reward== 100:
                    print(reward)

                ret += (gamma**i) * reward

            ## store average values at each iteration
            hyperparam_avgreturns.append(np.mean(run_avgreturns))
            hyperparam_avgvalues.append(np.mean(run_avgvals))
            hyperparam_avgepisodes.append(np.mean(run_avgepisode_length))
            hyperparam_avgepisodevalues.append(np.mean(run_avg_episode_values))

            hyperparam_stdreturns.append(np.std(run_avgreturns))
            hyperparam_stdvalues.append(np.std(run_avgvals))
            hyperparam_stdepisodes.append(np.std(run_avgepisode_length))
            hyperparam_stdepisodevalues.append(np.std(run_avg_episode_values))

        hyperparam_returns.append(run_returns)
        hyperparam_values.append(run_avg_episode_values)
        hyperparam_episodes.append(run_episode_length)

        np.save(files_name + 'hyperparam_avgreturns', hyperparam_avgreturns)
        np.save(files_name + 'hyperparam_avgepisodes', hyperparam_avgepisodes)
        np.save(files_name + 'hyperparam_avgepisodevalues', hyperparam_avgepisodevalues)

        np.save(files_name + 'hyperparam_stdreturns', hyperparam_stdreturns)
        np.save(files_name + 'hyperparam_stdepisodes', hyperparam_stdepisodes)
        np.save(files_name + 'hyperparam_stdepisodevalues', hyperparam_stdepisodevalues)

        np.save( files_name + 'hyperparam_returns', hyperparam_returns)
        np.save( files_name + 'hyperparam_values', hyperparam_values)
        np.save( files_name + 'hyperparam_episodes', hyperparam_episodes)

        hyperparam_final_avgreturns.append(hyperparam_returns)
        hyperparam_final_avgvalues.append(hyperparam_values)
        hyperparam_final_avgepisodes.append(hyperparam_episodes)

    # np.save(files_name + 'hyperparam_final_avgreturns', np.mean(hyperparam_final_avgreturns, axis=0))
    # np.save(files_name + 'hyperparam_final_avgvalues', np.mean(hyperparam_final_avgvalues, axis=0))
    # np.save(files_name + 'hyperparam_final_avgepisodes', np.mean(hyperparam_final_avgepisodes, axis=0))
    #
    # np.save(files_name + 'hyperparam_final_stdreturns', np.std(hyperparam_final_avgreturns, axis=0))
    # np.save(files_name + 'hyperparam_final_stdvalues', np.std(hyperparam_final_avgvalues, axis=0))
    # np.save(files_name + 'hyperparam_final_stdepisodes', np.std(hyperparam_final_avgepisodes, axis=0))

    np.save(files_name + 'hyperparam_final_avgreturns', np.mean(hyperparam_returns, axis=0))
    np.save(files_name + 'hyperparam_final_avgvalues', np.mean(hyperparam_values, axis=0))
    np.save(files_name + 'hyperparam_final_avgepisodes', np.mean(hyperparam_episodes, axis=0))

    np.save(files_name + 'hyperparam_final_stdreturns', np.std(hyperparam_returns, axis=0))
    np.save(files_name + 'hyperparam_final_stdvalues', np.std(hyperparam_values, axis=0))
    np.save(files_name + 'hyperparam_final_stdepisodes', np.std(hyperparam_episodes, axis=0))

def train_offline_online(data_dir, starting_state_path, alg_type, 
                         hyper_num, data_length_num, mem_size, num_rep, offline,
                         fqi_rep_num, num_step_ratio_mem, en,
                         feature, method_sarsa, num_epi_per_itr,
                         fqi_reg_type, initial_batch, rnd, 
                         num_updates_pretrain, epsilon_stop_training, status):

    print("offline_online", hyper_num, en,mem_size)

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

    num_steps = num_step_ratio_mem  # 200000

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

    ## normolize states
    def process_state(state, normalize=True):
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

        return states

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
    nnet_params = {"loss_features": 'next_state',  # "combined_mstde_next_reward", "combined_mstde_next_state", "reward", next_state, semi_MSTDE
                   "beta1": 0.0,
                   "beta2": 0.99,
                   "eps_init": 1.0,
                   "eps_final": 0.01,
                   "num_actions": num_act,
                   "replay_memory_size": mem_size,  # 200000 if using ER
                   "replay_init_size": 5000,
                   "batch_size": 32,
                   "fqi_reg_type": fqi_reg_type,  # "l2" or "prev"
                   }
    ## TTN
    hyper_sets_lstdq = OrderedDict([("nn_lr", np.power(10, [-3.0])),  # [-2.0, -2.5, -3.0, -3.5, -4.0]
                                    ("reg_A",
                                     [10, 20, 30, 50, 70, 100, 2, 3, 5, 8, 1, 0, 0.01, 0.002, 0.0003, 0.001, 0.05]),
                                    # [0.0, -1.0, -2.0, -3.0] can also do reg towards previous weights
                                    ("eps_decay_steps", [1]),
                                    ("update_freq", [1000]),
                                    ("data_length", [data_length]),
                                    ("fqi_rep", [fqi_rep]),
                                    ])

    files_name = "Offline-online//Training_{}_offlineonline_env_{}_mem_size_{}_date_{}_hyper_{}_training_{}".format(alg_type, en, mem_size,
                                                                                         datetime.today().strftime(
                                                                                             "%d_%m_%Y"), hyper_num, num_updates_pretrain
                                                                                         )
    if rnd:
        files_name = files_name + '_rnd'
    if initial_batch:
        files_name = files_name + '_initialbatch_'

    if alg == 'fqi':
        log_file = files_name + str(alg)
    if alg == 'dqn':
        log_file = files_name + str(alg)

    if alg in ("fqi"):
        hyper_sets = hyper_sets_lstdq
        TTN = True
    elif alg == "dqn":
        hyper_sets = hyper_sets_DQN
        TTN = False
    #
    hyperparams_all = list(itertools.product(*list(hyper_sets.values())))
    hyperparams = hyperparams_all

    times = []
    start_time = time.perf_counter()

    prev_action_flag = 1
    num_repeats = num_rep  # 10

    hyper = hyperparams[hyper_num]

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

    saved_state_list_all = np.load(starting_state_path)  # np.load starting states

    hyperparam_returns = []
    hyperparam_values = []
    hyperparam_episodes = []
    hyperparam_losses = []

    hyperparam_avgreturns = []
    hyperparam_avgvalues = []
    hyperparam_avgepisodes = []
    hyperparam_avgepisodevalues = []

    hyperparam_stdreturns = []
    hyperparam_stdvalues = []
    hyperparam_stdepisodes = []
    hyperparam_stdepisodevalues = []

    hyperparam_final_avgreturns = []
    hyperparam_final_avgvalues = []
    hyperparam_final_avgepisodes = []
    hyperparam_final_avgepisodevalues = []

    hyperparam_final_stdreturns = []
    hyperparam_final_stdvalues = []
    hyperparam_final_stdepisodes = []
    hyperparam_final_stdepisodevalues = []

    for rep in range(num_repeats):

        rand_seed = rep * 332 #32  # 332
        env.seed(rand_seed)
        T.manual_seed(rand_seed)
        np.random.seed(rand_seed)

        with open(log_file + ".txt", 'w') as f:
            print("Start! Seed: {}".format(rand_seed), file=f)

        if TTN:

            nn = TTNAgent_online_offline_mix(gamma, nnet_params=nnet_params, other_params=params,
                                             input_dims=input_dim, num_units_rep=128, dir=data_dir, offline=offline,
                                             num_tiling=16, num_tile=4, method_sarsa=method_sarsa,
                                             tilecoding=tilecoding, status=status)

        else:
            nn = DQNAgent(gamma, q_nnet_params, params, input_dims=input_dim, dir=data_dir, status=status)

        if initial_batch == False:

            if alg == 'dqn' or (TTN and nnet_params['replay_memory_size'] > 0):
                print("initialize buffer")
                frame_history = []
                prev_state = None
                prev_action = None
                done = 0
                state_unnormal = env.reset()
                state = process_state(state_unnormal)
                # populate the replay buffer
                while nn.memory.mem_cntr < nnet_params["replay_init_size"]:

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
                    prev_state = state
                    prev_action = action
                    state = new_state

        else:
            nn.memory.offline = True
            nn.memory.load_mem()

        prev_state = None
        prev_action = None

        run_returns = []
        run_vals = []
        run_episode_length = []
        run_avg_episode_values = []

        for itr in range(1):
            if not os.path.isfile("feature_{}_{}_{}".format(alg, en, mem_size) + ".pt"): # look for checkpoint.
                batch_size = 64
                for j in range(num_updates_pretrain): #num_updates_pretrain = num_epoch = 100
                    num_iteration_feature = int(mem_size / batch_size)
                    shuffle_index = np.arange(nnet_params['replay_memory_size'])
                    np.random.shuffle(shuffle_index)

                    for itr in range(num_iteration_feature):

                        if TTN:
                            # offline part.
                            nn.loss_features = "next_state"
                            loss = nn.learn_nn_feature_fqi(itr, shuffle_index)
                            print("Loss: ", loss.item())

                        else:
                            loss = nn.learn_nn_feature(itr, shuffle_index)
                            print("Loss: ", loss.item())

                if TTN:
                    T.save(nn.q_eval.state_dict(), "feature_{}_{}_{}".format(alg,
                                                                                en,
                                                                                mem_size) + ".pt")

                    T.save(nn.lin_weights, "lin_weights_{}_{}_{}".format(alg,
                                                                            en,
                                                                            mem_size) + ".pt")
                else:
                    T.save(nn.q_eval.state_dict(), "feature_{}_{}_{}".format(alg,
                                                                                en,
                                                                                mem_size) + ".pt")

                    T.save(nn.q_next.state_dict(), "feature_next_{}_{}_{}".format(alg,
                                                                                     en,
                                                                                     mem_size) + ".pt")

            else:
                if TTN:
                    nn.q_eval.load_state_dict(T.load("feature_{}_{}_{}".format(alg, en, mem_size) + ".pt"))
                    nn.lin_weights = T.load("lin_weights_{}_{}_{}".format(alg, en, mem_size) + ".pt")
                else:
                    nn.q_eval.load_state_dict(T.load("feature_{}_{}_{}".format(alg, en, mem_size) + ".pt"))
                    nn.q_next.load_state_dict(
                        T.load("feature_next_{}_{}_{}".format(alg, en, mem_size) + ".pt"))

            ## end of offline step
            run_avgreturns = []
            run_avgvals = []
            run_avgepisode_length = []

            done = 0
            episodes = 0
            val = 0.0
            q_values_episode = 0
            ret = 0
            episode_length = 0
            count_10epi = 0

            env.reset()
            # game = env.unwrapped
            # env.state = saved_state_list[count_10epi]
            # state_unnormal = env.state
            # state = process_state(state_unnormal)

            # state_unnormal = env.unwrapped.state
            state_unnormal = env.reset()
            state = process_state(state_unnormal)

            start_run_time = time.perf_counter()

            i = 0

            while episodes < num_epi_per_itr + 1:
                i += 1
                if done:
                    run_returns.append(ret)
                    run_vals.append(val)
                    run_episode_length.append(episode_length)
                    run_avg_episode_values.append((q_values_episode / episode_length))

                    run_avgreturns.append(ret)
                    run_avgvals.append(val)
                    run_avgepisode_length.append(episode_length)

                    print(episodes, i, round(val, 2), ret, "number episode from 10:", count_10epi,
                          "avegar over 10 episode:", round(np.mean(run_avgreturns), 3),
                          "avegare return across last 100 episodes:", round(np.mean(run_returns[-100:]), 3),
                          "state values:", (q_values_episode / episode_length), episode_length)

                    count_10epi += 1
                    episode_length = 0
                    q_values_episode = 0
                    val = 0.0
                    ret = 0.0
                    i = 0
                    episodes += 1

                    env.reset()

                    state_unnormal = env.reset()
                    state = process_state(state_unnormal)
                    if TTN:
                        nn.load_data()
                        nn.learn_pretrain()


                # Get action
                if TTN:
                    action = nn.choose_action(state)
                    q_values = nn.lin_values

                else:  # DQN
                    action, q_values = nn.choose_action(state)

                # run_values.append(T.mean(q_values.data, axis=1)[0].detach())
                q_values_episode += T.mean(q_values.data)

                # update parameters
                if prev_state is not None:
                    # prev_state_normal = process_state(prev_state)
                    # state_normal = process_state(state)
                    if prev_action_flag == 1:
                        nn.memory.store_transition_withnewaction(prev_state, np.squeeze(prev_action), reward, state,
                                                                 np.squeeze(action), int(done))
                    else:
                        nn.memory.store_transition(prev_state, np.squeeze(prev_action), reward, state, int(done))

                    if TTN:
                        # online part
                        nn.loss_features = "combined_mstde_next_state"
                        loss = nn.learn()

                    else:  # DQN
                        loss = nn.learn()

                    # run_losses.append(loss.detach())

                # do one step in the environment
                episode_length += 1
                new_state_unnormal, reward, done, info = env.step(np.array(action))  # action is a 1x1 matrix
                new_state = process_state(new_state_unnormal)

                # update saved states
                prev_state = state
                prev_action = action
                state = new_state  # action is a 1x1 matrix
                val += reward
                ret += (gamma ** i) * reward

            ## store average values at each iteration
            hyperparam_avgreturns.append(np.mean(run_avgreturns))
            hyperparam_avgvalues.append(np.mean(run_avgvals))
            hyperparam_avgepisodes.append(np.mean(run_avgepisode_length))
            hyperparam_avgepisodevalues.append(np.mean(run_avg_episode_values))

            hyperparam_stdreturns.append(np.std(run_avgreturns))
            hyperparam_stdvalues.append(np.std(run_avgvals))
            hyperparam_stdepisodes.append(np.std(run_avgepisode_length))
            hyperparam_stdepisodevalues.append(np.std(run_avg_episode_values))

        hyperparam_returns.append(run_returns)
        hyperparam_values.append(run_avg_episode_values)
        hyperparam_episodes.append(run_episode_length)

        np.save(files_name + 'hyperparam_avgreturns', hyperparam_avgreturns)
        np.save(files_name + 'hyperparam_avgepisodes', hyperparam_avgepisodes)
        np.save(files_name + 'hyperparam_avgepisodevalues', hyperparam_avgepisodevalues)

        np.save(files_name + 'hyperparam_stdreturns', hyperparam_stdreturns)
        np.save(files_name + 'hyperparam_stdepisodes', hyperparam_stdepisodes)
        np.save(files_name + 'hyperparam_stdepisodevalues', hyperparam_stdepisodevalues)

        np.save(files_name + 'hyperparam_returns', hyperparam_returns)
        np.save(files_name + 'hyperparam_values', hyperparam_values)
        np.save(files_name + 'hyperparam_episodes', hyperparam_episodes)

        hyperparam_final_avgreturns.append(hyperparam_returns)
        hyperparam_final_avgvalues.append(hyperparam_values)
        hyperparam_final_avgepisodes.append(hyperparam_episodes)

    # np.save(files_name + 'hyperparam_final_avgreturns', np.mean(hyperparam_final_avgreturns, axis=0))
    # np.save(files_name + 'hyperparam_final_avgvalues', np.mean(hyperparam_final_avgvalues, axis=0))
    # np.save(files_name + 'hyperparam_final_avgepisodes', np.mean(hyperparam_final_avgepisodes, axis=0))
    #
    # np.save(files_name + 'hyperparam_final_stdreturns', np.std(hyperparam_final_avgreturns, axis=0))
    # np.save(files_name + 'hyperparam_final_stdvalues', np.std(hyperparam_final_avgvalues, axis=0))
    # np.save(files_name + 'hyperparam_final_stdepisodes', np.std(hyperparam_final_avgepisodes, axis=0))

    np.save(files_name + 'hyperparam_final_avgreturns', np.mean(hyperparam_returns, axis=0))
    np.save(files_name + 'hyperparam_final_avgvalues', np.mean(hyperparam_values, axis=0))
    np.save(files_name + 'hyperparam_final_avgepisodes', np.mean(hyperparam_episodes, axis=0))

    np.save(files_name + 'hyperparam_final_stdreturns', np.std(hyperparam_returns, axis=0))
    np.save(files_name + 'hyperparam_final_stdvalues', np.std(hyperparam_values, axis=0))
    np.save(files_name + 'hyperparam_final_stdepisodes', np.std(hyperparam_episodes, axis=0))


def train_offline(data_dir, starting_state_path, alg_type, hyper_num, data_length_num, mem_size, num_rep, offline,
                 fqi_rep_num, num_step_ratio_mem, en,
                 feature, method_sarsa, num_epi_per_itr,
                 fqi_reg_type, initial_batch, rnd, num_updates_pretrain, epsilon_stop_training, status):


    print("offline", hyper_num, en, mem_size)

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

    num_steps = num_step_ratio_mem  # 200000

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

    # rand_seed = num_rep * 32  # 332
    # env.seed(rand_seed)
    # T.manual_seed(rand_seed)
    # np.random.seed(rand_seed)

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

        return states

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
                   "fqi_reg_type": fqi_reg_type,  # "l2" or "prev"
                   }
    ## TTN
    hyper_sets_lstdq = OrderedDict([("nn_lr", np.power(10, [-3.0])),  # [-2.0, -2.5, -3.0, -3.5, -4.0]
                                    ("reg_A",
                                     [10, 20, 30, 50, 70, 100, 2, 3, 5, 8, 1, 0, 0.01, 0.002, 0.0003, 0.001, 0.05]),
                                    # [0.0, -1.0, -2.0, -3.0] can also do reg towards previous weights
                                    ("eps_decay_steps", [1]),
                                    ("update_freq", [1000]),
                                    ("data_length", [data_length]),
                                    ("fqi_rep", [fqi_rep]),
                                    ])

    files_name = "Offline//Training_{}_offline_env_{}_mem_size_{}_date_{}_hyper_{}_training_{}".format(alg_type, en, mem_size,
                                                                                         datetime.today().strftime(
                                                                                             "%d_%m_%Y"), hyper_num, num_updates_pretrain
                                                                                         )
    if rnd:
        files_name = files_name + '_rnd'

    if initial_batch:
        files_name = files_name + '_initialbatch_'

    if alg == 'fqi':
        log_file = files_name + str(alg)
    if alg == 'dqn':
        log_file = files_name + str(alg)

    if alg in ("fqi"):
        hyper_sets = hyper_sets_lstdq
        TTN = True
    elif alg == "dqn":
        hyper_sets = hyper_sets_DQN
        TTN = False
    #
    hyperparams_all = list(itertools.product(*list(hyper_sets.values())))
    hyperparams = hyperparams_all

    times = []
    start_time = time.perf_counter()

    prev_action_flag = 1
    num_repeats = num_rep  # 10

    hyper = hyperparams[hyper_num]

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

    saved_state_list_all = np.load(starting_state_path)  # np.load starting states

    hyperparam_returns = []
    hyperparam_values = []
    hyperparam_episodes = []
    hyperparam_losses = []

    hyperparam_avgreturns = []
    hyperparam_avgvalues = []
    hyperparam_avgepisodes = []
    hyperparam_avgepisodevalues = []

    hyperparam_stdreturns = []
    hyperparam_stdvalues = []
    hyperparam_stdepisodes = []
    hyperparam_stdepisodevalues = []

    hyperparam_final_avgreturns = []
    hyperparam_final_avgvalues = []
    hyperparam_final_avgepisodes = []
    hyperparam_final_avgepisodevalues = []

    hyperparam_final_stdreturns = []
    hyperparam_final_stdvalues = []
    hyperparam_final_stdepisodes = []
    hyperparam_final_stdepisodevalues = []

    for rep in range(num_repeats):

        rand_seed = rep * 32  # 332
        env.seed(rand_seed)
        T.manual_seed(rand_seed)
        np.random.seed(rand_seed)

        with open(log_file + ".txt", 'w') as f:
            print("Start! Seed: {}".format(rand_seed), file=f)

        if TTN:
            nn = TTNAgent_online_offline_mix(gamma, nnet_params=nnet_params, other_params=params,
                                             input_dims=input_dim, num_units_rep=128, dir=data_dir, offline=offline,
                                             num_tiling=16, num_tile=4, method_sarsa=method_sarsa,
                                             tilecoding=tilecoding, status=status)

        else:
            nn = DQNAgent(gamma, q_nnet_params, params, input_dims=input_dim, dir=data_dir, status=status)

        if initial_batch == False:
            if alg == 'dqn' or (TTN and nnet_params['replay_memory_size'] > 0):
                print("initialize buffer")
                frame_history = []
                prev_state = None
                prev_action = None
                done = 0
                state_unnormal = env.reset()
                state = process_state(state_unnormal)
                # populate the replay buffer
                while nn.memory.mem_cntr < nnet_params["replay_init_size"]:

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
                    prev_state = state
                    prev_action = action
                    state = new_state

        else:
            nn.memory.offline = True
            nn.memory.load_mem()

        prev_state = None
        prev_action = None

        run_returns = []
        run_vals = []
        run_episode_length = []
        run_avg_episode_values = []

        run_losses = []

        for itr in range(1):
            ## do offline-step update before running the agent
            if not os.path.isfile("feature_{}_{}_{}".format(alg, en, mem_size) + ".pt"):
                batch_size = 64
                for j in range(num_updates_pretrain): #num_updates_pretrain = num_epoch = 100
                    num_iteration_feature = int(mem_size / batch_size)
                    shuffle_index = np.arange(nnet_params['replay_memory_size'])
                    np.random.shuffle(shuffle_index)

                    for itr in range(num_iteration_feature):
                        if TTN:
                            loss = nn.learn_nn_feature_fqi(itr, shuffle_index)
                            print(loss)

                        else:
                            loss = nn.learn_nn_feature(itr, shuffle_index)
                            print(loss)

                if TTN:
                    T.save(nn.q_eval.state_dict(), "feature_{}_{}_{}_{}".format(alg,
                                                                                en,
                                                                                mem_size, num_updates_pretrain) + ".pt")

                    T.save(nn.lin_weights, "lin_weights_{}_{}_{}_{}".format(alg,
                                                                            en,
                                                                            mem_size, num_updates_pretrain) + ".pt")
                else:
                    T.save(nn.q_eval.state_dict(), "feature_{}_{}_{}_{}".format(alg,
                                                                                en,
                                                                            mem_size, num_updates_pretrain) + ".pt")
                    T.save(nn.q_next.state_dict(), "feature_next_{}_{}_{}_{}".format(alg,
                                                                                en,
                                                                                mem_size, num_updates_pretrain) + ".pt")

            else:
                if TTN:
                    nn.q_eval.load_state_dict(T.load("feature_{}_{}_{}".format(alg, en, mem_size) + ".pt"))
                    nn.lin_weights = T.load("lin_weights_{}_{}_{}".format(alg, en, mem_size) + ".pt")
                else:
                    nn.q_eval.load_state_dict(T.load("feature_{}_{}_{}".format(alg, en, mem_size) + ".pt"))
                    nn.q_next.load_state_dict(
                        T.load("feature_next_{}_{}_{}".format(alg, en, mem_size) + ".pt"))
            ##
            ## end of offline step

            run_avgreturns = []
            run_avgvals = []
            run_avgepisode_length = []

            done = 0
            episodes = 0
            val = 0.0
            q_values_episode = 0
            ret = 0
            episode_length = 0
            count_10epi = 0

            env.reset()
            # game = env.unwrapped
            # env.state = saved_state_list[count_10epi]
            # state_unnormal = env.state
            # state = process_state(state_unnormal)

            # state_unnormal = env.unwrapped.state
            state_unnormal = env.reset()
            state = process_state(state_unnormal)

            start_run_time = time.perf_counter()

            i = 0

            while episodes < num_epi_per_itr + 1:

                i += 1

                if done:
                    run_returns.append(ret)
                    run_vals.append(val)
                    run_episode_length.append(episode_length)
                    run_avg_episode_values.append((q_values_episode / episode_length))

                    run_avgreturns.append(ret)
                    run_avgvals.append(val)
                    run_avgepisode_length.append(episode_length)

                    print(episodes, i, round(val, 2), ret, "number episode from 10:", count_10epi,
                          "avegar over 10 episode:", round(np.mean(run_avgreturns), 3),
                          "avegare return across last 100 episodes:", round(np.mean(run_returns[-100:]), 3),
                          "state values:", (q_values_episode / episode_length), episode_length)

                    count_10epi += 1
                    episode_length = 0
                    q_values_episode = 0
                    val = 0.0
                    ret = 0.0
                    i = 0
                    episodes += 1

                    env.reset()
                    # env.state = saved_state_list[count_10epi]
                    # state_unnormal = env.state
                    # state = process_state(state_unnormal)

                    # state_unnormal = env.unwrapped.state
                    state_unnormal = env.reset()
                    state = process_state(state_unnormal)

                # Get action
                if TTN:
                    action = nn.choose_action(state)
                    q_values = nn.lin_values

                else:  # DQN
                    action, q_values = nn.choose_action(state)

                # run_values.append(T.mean(q_values.data, axis=1)[0].detach())
                q_values_episode += T.mean(q_values.data)

                # update parameters and add to the memory
                # .....

                # do one step in the environment
                episode_length += 1
                new_state_unnormal, reward, done, info = env.step(np.array(action))  # action is a 1x1 matrix
                new_state = process_state(new_state_unnormal)

                # update saved states
                prev_state = state
                prev_action = action
                state = new_state  # action is a 1x1 matrix
                val += reward
                ret += (gamma ** i) * reward

            ## store average values at each iteration
            hyperparam_avgreturns.append(np.mean(run_avgreturns))
            hyperparam_avgvalues.append(np.mean(run_avgvals))
            hyperparam_avgepisodes.append(np.mean(run_avgepisode_length))
            hyperparam_avgepisodevalues.append(np.mean(run_avg_episode_values))

            hyperparam_stdreturns.append(np.std(run_avgreturns))
            hyperparam_stdvalues.append(np.std(run_avgvals))
            hyperparam_stdepisodes.append(np.std(run_avgepisode_length))
            hyperparam_stdepisodevalues.append(np.std(run_avg_episode_values))

        hyperparam_returns.append(run_returns)
        hyperparam_values.append(run_avg_episode_values)
        hyperparam_episodes.append(run_episode_length)

        np.save(files_name + 'hyperparam_avgreturns', hyperparam_avgreturns)
        np.save(files_name + 'hyperparam_avgepisodes', hyperparam_avgepisodes)
        np.save(files_name + 'hyperparam_avgepisodevalues', hyperparam_avgepisodevalues)

        np.save(files_name + 'hyperparam_stdreturns', hyperparam_stdreturns)
        np.save(files_name + 'hyperparam_stdepisodes', hyperparam_stdepisodes)
        np.save(files_name + 'hyperparam_stdepisodevalues', hyperparam_stdepisodevalues)

        np.save(files_name + 'hyperparam_returns', hyperparam_returns)
        np.save(files_name + 'hyperparam_values', hyperparam_values)
        np.save(files_name + 'hyperparam_episodes', hyperparam_episodes)

        hyperparam_final_avgreturns.append(hyperparam_returns)
        hyperparam_final_avgvalues.append(hyperparam_values)
        hyperparam_final_avgepisodes.append(hyperparam_episodes)

    # np.save(files_name + 'hyperparam_final_avgreturns', np.mean(hyperparam_final_avgreturns, axis=0))
    # np.save(files_name + 'hyperparam_final_avgvalues', np.mean(hyperparam_final_avgvalues, axis=0))
    # np.save(files_name + 'hyperparam_final_avgepisodes', np.mean(hyperparam_final_avgepisodes, axis=0))
    #
    # np.save(files_name + 'hyperparam_final_stdreturns', np.std(hyperparam_final_avgreturns, axis=0))
    # np.save(files_name + 'hyperparam_final_stdvalues', np.std(hyperparam_final_avgvalues, axis=0))
    # np.save(files_name + 'hyperparam_final_stdepisodes', np.std(hyperparam_final_avgepisodes, axis=0))

    np.save(files_name + 'hyperparam_final_avgreturns', np.mean(hyperparam_returns, axis=0))
    np.save(files_name + 'hyperparam_final_avgvalues', np.mean(hyperparam_values, axis=0))
    np.save(files_name + 'hyperparam_final_avgepisodes', np.mean(hyperparam_episodes, axis=0))

    np.save(files_name + 'hyperparam_final_stdreturns', np.std(hyperparam_returns, axis=0))
    np.save(files_name + 'hyperparam_final_stdvalues', np.std(hyperparam_values, axis=0))
    np.save(files_name + 'hyperparam_final_stdepisodes', np.std(hyperparam_episodes, axis=0))