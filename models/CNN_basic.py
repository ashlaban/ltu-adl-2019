"""
CNN with 3 conv layers and a fully connected classification layer
"""

import torch.nn as nn


class Flatten(nn.Module):
    def forward(self, x):
        x = x.view(x.size()[0], -1)
        return x


class CNN_basic(nn.Module):
    """
    :var conv1   : torch.nn.Conv2d
    :var conv2   : torch.nn.Conv2d
    :var conv3   : torch.nn.Conv2d
        The first three convolutional layers of the network

    :var fc      : torch.nn.Linear
        Final fully connected layer
    """

    def __init__(self, output_channels=10, input_channels=3, **kwargs):
        """
        :param output_channels: the number of classes in the dataset
        """
        super(CNN_basic, self).__init__()

        self.expected_input_size = (32, 32)

        # First layer
        self.conv1 = nn.Sequential(
            nn.Conv2d(input_channels, 24, kernel_size=5, stride=3),
            nn.LeakyReLU()
        )
        # Second layer
        self.conv2 = nn.Sequential(
            nn.Conv2d(24, 48, kernel_size=3, stride=2),
            nn.LeakyReLU()
        )
        # Third layer
        self.conv3 = nn.Sequential(
            nn.Conv2d(48, 72, kernel_size=3, stride=1),
            nn.LeakyReLU()
        )

        # Classification layer
        self.fc = nn.Sequential(
            Flatten(),
            nn.Linear(288, output_channels)
        )

    def forward(self, x):
        """
        Computes forward pass on the network
        :param x: torch.Tensor
            The input to the model
        :return: torch.Tensor
            Activations of the fully connected layer
        """
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        x = self.fc(x)
        return x
