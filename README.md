# offline-online-representation-learning
This is the repository for Offline-Online Representation Learning for Reinforcement Learning.

The base code is heavily borrowed from: <a href="">HERE</a>.

Run the code first to generate an offline dataset.

```
python create_data.py --hyper_num 15 --mem_size 1000 --num_step_ratio_mem 50000 --en 'Mountaincar'
```

Once the dataset has been created (stored as a buffer) in the `Data` folder. Then run the following code to train in either online, offline or offline-online.

```
python create_data.py --offline_online_training 'offline_online' --tr_hyper_num 15 
```

## Loss Functions
There are several options to change the loss functions. The base loss is MSTDE, which can be swapped with either `next_state`, or `reward`. To change the loss function, go to file `training3.py` and in function `train_offline_online()`, set the TTN params as follows.

```
## TTN
nnet_params = {"loss_features": 'reward',  # change to either next_state, or semi_MSTDE here.
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
```
