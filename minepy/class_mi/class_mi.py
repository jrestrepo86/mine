#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

import numpy as np
import torch
import torch.nn as nn
from torch.optim.lr_scheduler import ReduceLROnPlateau
from tqdm import tqdm

from minepy.class_mi.class_mi_tools import class_mi_batch
from minepy.minepy_tools import EarlyStopping, get_activation_fn, toColVector

EPS = 1e-6


class ClassMI(nn.Module):
    def __init__(
        self, input_dim, hidden_dim=50, num_hidden_layers=2, afn="elu", device=None
    ):
        super().__init__()
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        torch.device(self.device)

        activation_fn = get_activation_fn(afn)
        seq = [nn.Linear(input_dim, hidden_dim), activation_fn()]
        for _ in range(num_hidden_layers):
            seq += [nn.Linear(hidden_dim, hidden_dim), activation_fn()]
        seq += [nn.Linear(hidden_dim, 1)]
        self.model = nn.Sequential(*seq)
        self.model = self.model.to(self.device)

    def forward(self, x, z, x_marg, z_marg):
        n = x.shape[0]

        # samples from joint distribution
        s_joint = torch.cat((x, z), dim=1)
        # samples from product of marginal distribution
        s_marg = torch.cat((x_marg, z_marg), dim=1)

        samples = torch.cat((s_joint, s_marg), dim=0)
        labels = torch.cat((torch.ones(n), torch.zeros(n)), dim=0).to(x.device)

        # random ordering
        inds = torch.randperm(2 * n)
        samples = samples[inds, :]
        labels = labels[inds]

        logit = torch.squeeze(self.model(samples))
        probs = torch.sigmoid(logit)

        return logit, labels, probs

    def fit(
        self,
        X,
        Z,
        batch_size=64,
        max_epochs=2000,
        val_size=0.2,
        lr=1e-4,
        lr_factor=0.1,
        lr_patience=10,
        stop_patience=100,
        stop_min_delta=0.05,
        weight_decay=5e-5,
        verbose=False,
    ):
        opt = torch.optim.Adam(
            self.model.parameters(),
            lr=lr,
            weight_decay=weight_decay,
            betas=(0.9, 0.999),
        )
        scheduler = ReduceLROnPlateau(
            opt, mode="min", factor=lr_factor, patience=lr_patience, verbose=verbose
        )

        early_stopping = EarlyStopping(
            patience=stop_patience, delta=int(stop_min_delta)
        )

        X = torch.from_numpy(toColVector(X.astype(np.float32)))
        Z = torch.from_numpy(toColVector(Z.astype(np.float32)))

        N, _ = X.shape

        val_size = int(val_size * N)
        inds = np.random.permutation(N)
        (
            val_idx,
            train_idx,
        ) = (
            inds[:val_size],
            inds[val_size:],
        )
        Xval, Xtrain = X[val_idx, :], X[train_idx, :]
        Zval, Ztrain = Z[val_idx, :], Z[train_idx, :]

        Xval = Xval.to(self.device)
        Xtrain = Xtrain.to(self.device)
        Zval = Zval.to(self.device)
        Ztrain = Ztrain.to(self.device)
        self.X = X.to(self.device)
        self.Z = Z.to(self.device)

        self.loss_fn = nn.BCEWithLogitsLoss()
        val_loss_epoch = []
        train_loss_epoch = []
        train_acc_epoch = []
        val_acc_epoch = []
        val_dkl = []
        train_dkl = []

        for i in tqdm(range(max_epochs), disable=not verbose):
            # training
            self.train()
            for x, z, x_marg, z_marg in class_mi_batch(
                Xtrain, Ztrain, batch_size=batch_size
            ):
                # x = x.to(self.device)
                # z = z.to(self.device)
                opt.zero_grad()
                with torch.set_grad_enabled(True):
                    logits, labels, _ = self.forward(x, z, x_marg, z_marg)
                    loss = self.loss_fn(logits, labels)
                    loss.backward()
                    opt.step()

            # validate and testing
            torch.set_grad_enabled(False)
            self.eval()
            with torch.no_grad():
                dkl, loss, acc = self.calc_mi_fn(Xtrain, Ztrain)
                train_dkl.append(dkl.item())
                train_loss_epoch.append(loss.item())
                train_acc_epoch.append(acc.item())
                dkl, loss, acc = self.calc_mi_fn(Xval, Zval)
                val_dkl.append(dkl.item())
                val_loss_epoch.append(loss.item())
                val_acc_epoch.append(acc.item())
                # learning rate scheduler
                scheduler.step(acc.item())
                # early stopping
                early_stopping(-acc)

            if early_stopping.early_stop:
                break

        self.train_dkl = np.array(train_dkl)
        self.train_loss_epoch = np.array(train_loss_epoch)
        self.train_acc_epoch = np.array(train_acc_epoch)
        self.val_dkl = np.array(val_dkl)
        self.val_loss_epoch = np.array(val_loss_epoch)
        self.val_acc_epoch = np.array(val_acc_epoch)

    def calc_mi_fn(self, x, z):
        n = len(x)
        x_marg = x[torch.randperm(n)].to(self.device)
        z_marg = z[torch.randperm(n)].to(self.device)
        logit, labels, probs = self.forward(x, z, x_marg, z_marg)
        # get loss function
        loss = self.loss_fn(logit, labels)
        # Calculate accuracy
        y_pred = torch.round(probs)
        acc = torch.sum(y_pred == labels) / labels.shape[0]

        labels = labels > 0
        likel_ratio_p = (probs[labels] + EPS) / (1 - probs[labels] - EPS)
        likel_ratio_q = (probs[torch.logical_not(labels)] + EPS) / (
            1 - probs[torch.logical_not(labels)] - EPS
        )
        fp = torch.log(torch.abs(likel_ratio_p))
        fq = torch.log(torch.abs(likel_ratio_q))

        Dkl = fp.mean() - (torch.logsumexp(fq, 0) - math.log(fq.shape[0]))
        return Dkl, loss, acc

    def get_mi(self):
        mi, _, _ = self.calc_mi_fn(self.X, self.Z)
        return mi

    def get_curves(self):
        return (
            self.train_dkl,
            self.val_dkl,
            self.train_loss_epoch,
            self.val_loss_epoch,
            self.train_acc_epoch,
            self.val_acc_epoch,
        )