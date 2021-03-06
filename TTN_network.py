import os
import torch as T
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
from torch.autograd import Variable

class TTNNetwork(nn.Module):
    def __init__(self, beta1, beta2, lr, n_actions, input_dims, number_unit=128, num_units_rep=128):
        super(TTNNetwork, self).__init__()

        self.input_dims = input_dims
        self.fc1 = nn.Linear(input_dims, number_unit, bias=True)
        self.fc2 = nn.Linear(number_unit, number_unit, bias=True)
        self.fc3 = nn.Linear(number_unit, num_units_rep, bias=True) # the representation layer
        self.fc4 = nn.Linear(num_units_rep, n_actions, bias=True) # the prediction layer
        self.fc5 = nn.Linear(num_units_rep, n_actions, bias=True) # reward layer
        self.fc6 = nn.Linear(num_units_rep, n_actions*input_dims, bias=True) # the state-prediction layer

        self.fc1.bias.data.fill_(0.0)
        self.fc2.bias.data.fill_(0.0)
        self.fc3.bias.data.fill_(0.0)
        self.fc4.bias.data.fill_(0.0)
        self.fc5.bias.data.fill_(0.0)

        nn.init.xavier_uniform_(self.fc1.weight)
        nn.init.xavier_uniform_(self.fc2.weight)
        nn.init.xavier_uniform_(self.fc3.weight)
        nn.init.xavier_uniform_(self.fc4.weight)
        nn.init.xavier_uniform_(self.fc5.weight)
        nn.init.xavier_uniform_(self.fc6.weight)

        self.optimizer = optim.Adam(self.parameters(), lr=lr, betas=(beta1, beta2), eps=1e-08, weight_decay=0, amsgrad=True)
        self.loss = nn.MSELoss()

        self.device = T.device('cuda:0' if T.cuda.is_available() else 'cpu')
        self.to(self.device)

    def forward(self, state):
        # x = state
        """
        Build a network that maps state -> value-predictions, features, pred_states.
        """
        x = F.relu(self.fc1(state))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))  # representation layer
        self.predictions = self.fc4(x) # Q-prediction layer
        self.rewards = self.fc5(x) # rewards layer
        self.pred_states = self.fc6(x) # state-prediction layer
        return self.predictions, x, self.pred_states, self.rewards

    def save_checkpoint(self):
        print('... saving checkpoint ...')
        T.save(self.state_dict(), self.checkpoint_file)

    def load_checkpoint(self):
        print('... loading checkpoint ...')
        self.load_state_dict(T.load(self.checkpoint_file))


# class TTNNetwork_image(nn.Module):
#     def __init__(self, lr, n_actions, name, input_dims, chkpt_dir):
#         super(TTNNetwork_image, self).__init__()
#         self.checkpoint_dir = chkpt_dir
#         self.checkpoint_file = os.path.join(self.checkpoint_dir, name)
#
#         self.conv1 = nn.Conv2d(input_dims[0], 32, 8, stride=4)
#         self.conv2 = nn.Conv2d(32, 64, 4, stride=2)
#         self.conv3 = nn.Conv2d(64, 64, 3, stride=1)
#
#         fc_input_dims = self.calculate_conv_output_dims(input_dims)
#
#         self.fc1 = nn.Linear(fc_input_dims, 512)
#         self.fc2 = nn.Linear(512, n_actions)
#
#         self.optimizer = optim.RMSprop(self.parameters(), lr=lr)
#
#         self.loss = nn.MSELoss()
#         self.device = T.device('cuda:0' if T.cuda.is_available() else 'cpu')
#         self.to(self.device)
#
#     def calculate_conv_output_dims(self, input_dims):
#         state = T.zeros(1, *input_dims)
#         dims = self.conv1(state)
#         dims = self.conv2(dims)
#         dims = self.conv3(dims)
#         return int(np.prod(dims.size()))
#
#     def forward(self, state):
#         conv1 = F.relu(self.conv1(state))
#         conv2 = F.relu(self.conv2(conv1))
#         conv3 = F.relu(self.conv3(conv2))
#         # conv3 shape is BS x n_filters x H x W
#         conv_state = conv3.view(conv3.size()[0], -1)
#         # conv_state shape is BS x (n_filters * H * W)
#         flat1 = F.relu(self.fc1(conv_state))
#         actions = self.fc2(flat1)
#
#         return actions
#
#     def save_checkpoint(self):
#         print('... saving checkpoint ...')
#         T.save(self.state_dict(), self.checkpoint_file)
#
#     def load_checkpoint(self):
#         print('... loading checkpoint ...')
#         self.load_state_dict(T.load(self.checkpoint_file))
