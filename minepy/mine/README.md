# Minepy

## Mine Module

This module contains the implementation of MINE.
([Complete Test of this module](../../tests/test_mine/README.md))

### Usage example:

```py
import numpy as np
from matplotlib import pyplot as plt
from minepy.mine.mine import Mine

# Generate Gaussian Data
rho = 0.5
mu = np.array([0, 0])
nDataPoints = 5000
cov_matrix = np.array([[1, rho], [rho, 1]])
joint_samples_train = np.random.multivariate_normal(
    mean=mu, cov=cov_matrix, size=(nDataPoints, 1)
)
X = np.squeeze(joint_samples_train[:, :, 0])
Y = np.squeeze(joint_samples_train[:, :, 1])

mi_teo = -0.5 * np.log(1 - rho**2)  # Theoretical MI Value

# Mine
model_params = {"hidden_dim": 50, "num_hidden_layers": 3, "afn": "elu", "loss": "mine"}
train_params = {
    "batch_size": "full",
    "max_epochs": 5000,
    "val_size": 0.2,
    "lr": 1e-3,
    "lr_factor": 0.1,
    "lr_patience": 100,
    "stop_patience": 200,
    "stop_min_delta": 0.0,
    "verbose": True,
}
# Generate model
model = Mine(X, Y, **model_params)
# Train models
model.fit(**train_params)
# Get mi estimation
mi = model.get_mi()
# Get loss and mi curves
val_loss, val_loss_smoothed, val_mi, test_mi = model.get_curves()
# plot
fig, axs = plt.subplots(2, 1, sharex=True, sharey=False)
axs[0].plot(val_loss, "b", label="Validation loss")
axs[0].plot(val_loss_smoothed, "r", label="Smoothed validation loss")
axs[0].set_ylabel("Loss")
axs[1].plot(val_mi, "b", label="Validation MI")
axs[1].plot(test_mi, "r", label="Test MI")
axs[1].set_xlabel("epochs")
axs[1].set_ylabel("MI")
fig.suptitle(
    f"Mutual information neural estimation,\n Theoretical MI={mi_teo:.2f}, Estimated MI={mi:.2f} ",
    fontsize=13,
)
plt.show()
```
