#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Sep 25 09:40:30 2019

@author: paul
"""
import numpy as np

class baseModel(object):
    def set_parameters(self, **kwargs):

        # hyperparameters
        self.hyperparameters = kwargs

        # hyperparameters for randomized search
        self.hyperparameters_search = {}

        for key in self.hyperparameters.keys():
            if type(self.hyperparameters[key]) is list:
                if len(self.hyperparameters[key])>0:
                    self.hyperparameters_search[key] = self.hyperparameters[key].copy()


    def fit_RandomizedSearch(self, trainX, trainy,  n_iter=10, **kwargs):
        # check if hyperparameters where provided in lists for randomized search
        if len(self.hyperparameters_search) == 0:
            raise Exception("No variable indicated for hyperparameter search!")

        #iterate with randomized hyperparameters
        best_loss = np.inf
        for i in range(n_iter):
            print(f"Search iteration Nr {i+1}/{n_iter}")

            # random selection of hyperparameters
            for key in self.hyperparameters_search.keys():
                low = self.hyperparameters_search[key][0]
                high = self.hyperparameters_search[key][1]

                if type(low) is float and type(high) is float:
                    self.hyperparameters[key] = np.random.uniform(low, high)

                if type(low) is int and type(high) is int:
                    self.hyperparameters[key] = np.random.randint(low, high+1)

                if type(low) is tuple and type(high) is tuple:
                    hyp_list = []
                    for i in range(len(low)):
                        hyp_list.append(np.random.randint(low[i], high[i]+1))
                    self.hyperparameters[key] = tuple(hyp_list)

            self.fit(trainX, trainy, **kwargs)

            # check if validation score was enhanced
            if self.mean_val_loss<best_loss:
                best_loss = self.mean_val_loss
                self.best_hyperparameters = self.hyperparameters.copy()

                print("New best hyperparameters")
                print(f"Mean loss: {best_loss}")
                print(self.best_hyperparameters)

        # refit the model with optimized hyperparameter
        # AND to have the weights of the DE for the best hyperparameters again
        print("Refit the model with best hyperparamters")

        self.hyperparameters = self.best_hyperparameters.copy()
        print(self.hyperparameters)
        self.fit(trainX, trainy, **kwargs)

        print(f"best loss search: {best_loss}")
        print(f"loss refitting : {self.mean_val_loss}")


    def fit(self):
        raise NameError("Function 'fit' is not defined!")

    def predict(self):
        raise NameError("Function 'fit' is not defined!")

    def save(self):
        raise NameError("Function 'save' is not defined!")

    def load(self):
        raise NameError("Function 'load' is not defined!")



# =============================================================================
# =============================================================================
# =============================================================================
#
# =============================================================================
# =============================================================================
# =============================================================================

import keras.backend as K
from keras.models import Model, save_model, load_model
from keras.layers import Dense, Input, concatenate
from keras.layers import Dropout, GaussianNoise
from keras.optimizers import Adam
from keras.callbacks import EarlyStopping
from keras import regularizers

from os.path import join, exists
from os import mkdir, listdir, getcwd
from shutil import rmtree

from ninolearn.learn.losses import nll_gaussian, nll_skewed_gaussian
from ninolearn.learn.skillMeasures import rmse
from ninolearn.utils import print_header, small_print_header
from ninolearn.exceptions import MissingArgumentError

import warnings

import time

class DEM(baseModel):
    """
    A deep ensemble model (DEM) predicting  either mean or mean and standard
    deviation with one hidden layer having the ReLU function as activation for
    the hidden layer. It is trained using the MSE or negative-log-likelihood of
    a gaussian distribution, respectively.
    """

    def __del__(self):
        K.clear_session()

    def get_model_desc(self, pdf):
        """
        Assignes sum weights description to the model depending on which
        predicted distribution is selected.
        """
        if pdf=="normal":
            self.loss = nll_gaussian
            self.loss_name = 'nll_gaussian'
            self.n_outputs = 2
            self.output_names =  ['mean', 'std']

        elif pdf=="skewed":
            self.loss = nll_skewed_gaussian
            self.loss_name = 'nll_skewed_gaussian'
            self.n_outputs = 3
            self.output_names =  ['location', 'scale', 'shape']

        elif pdf is None:
            self.loss = 'mse'
            self.loss_name = 'mean_squared_error'
            self.n_outputs = 1
            self.output_names =  ['prediction']


    def build_model(self, n_features):
        """
        The method builds a new member of the ensemble and returns it.
        """
        # derived parameters
        self.hyperparameters['n_members'] = self.hyperparameters['n_segments'] * self.hyperparameters['n_members_segment']
        self.get_model_desc(self.hyperparameters['pdf'])

        # initialize optimizer and early stopping
        self.optimizer = Adam(lr=self.hyperparameters['lr'], beta_1=0.9, beta_2=0.999, epsilon=None, decay=0., amsgrad=False)
        self.es = EarlyStopping(monitor=f'val_{self.loss_name}', min_delta=0.0, patience=self.hyperparameters['patience'], verbose=1,
                   mode='min', restore_best_weights=True)

        inputs = Input(shape=(n_features,))
        h = GaussianNoise(self.hyperparameters['noise_in'],
                          name='noise_input')(inputs)

        for i in range(self.hyperparameters['layers']):
            h = Dense(self.hyperparameters['neurons'], activation='relu',
                      kernel_regularizer=regularizers.l1_l2(self.hyperparameters['l1_hidden'],
                                                            self.hyperparameters['l2_hidden']),
                      kernel_initializer='random_uniform',
                      bias_initializer='zeros',
                      name=f'hidden_{i}')(h)

            h = Dropout(self.hyperparameters['dropout'],
                        name=f'hidden_dropout_{i}')(h)


        mu = Dense(1, activation='linear',
                   kernel_regularizer=regularizers.l1_l2(self.hyperparameters['l1_mu'],
                                                         self.hyperparameters['l2_mu']),
                   kernel_initializer='random_uniform',
                   bias_initializer='zeros',
                   name='mu_output')(h)

        mu = GaussianNoise(self.hyperparameters['noise_mu'],
                           name='noise_mu')(mu)


        if self.hyperparameters['pdf']=='normal' or self.hyperparameters['pdf']=='skewed':
            sigma = Dense(1, activation='softplus',
                          kernel_regularizer=regularizers.l1_l2(self.hyperparameters['l1_sigma'],
                                                                self.hyperparameters['l2_sigma']),
                          kernel_initializer='random_uniform',
                          bias_initializer='zeros',
                          name='sigma_output')(h)
            sigma = GaussianNoise(self.hyperparameters['noise_sigma'],
                                  name='noise_sigma')(sigma)

        if self.hyperparameters['pdf']=='skewed':
            alpha = Dense(1, activation='linear',
                       kernel_regularizer=regularizers.l1_l2(self.hyperparameters['l1_alpha'],
                                                             self.hyperparameters['l2_alpha']),
                       kernel_initializer='random_uniform',
                       bias_initializer='zeros',
                       name='alpha_output')(h)

            alpha = GaussianNoise(self.hyperparameters['noise_alpha'],
                           name='noise_alpha')(alpha)

        if self.hyperparameters['pdf'] is None:
            outputs = mu
        elif self.hyperparameters['pdf']=='normal':
            outputs = concatenate([mu, sigma])
        elif self.hyperparameters['pdf']=='skewed':
            outputs = concatenate([mu, sigma, alpha])

        model = Model(inputs=inputs, outputs=outputs)
        return model


    def fit(self, trainX, trainy, valX=None, valy=None, use_pretrained=False):
        """
        Fit the model to training data
        """

        start_time = time.time()
        # clear memory
        K.clear_session()

        # allocate lists for the ensemble
        self.ensemble = []
        self.history = []
        self.val_loss = []

        self.segment_len = trainX.shape[0]//self.hyperparameters['n_segments']

        if self.hyperparameters['n_segments']==1 and (valX is not None or valy is not None):
             warnings.warn("Validation and test data set are the same if n_segements is 1!")

        i = 0
        while i<self.hyperparameters['n_members_segment']:
            j = 0
            while j<self.hyperparameters['n_segments']:
                ensemble_member = self.build_model(trainX.shape[1])

                n_ens_sel = len(self.ensemble)
                small_print_header(f"Train member Nr {n_ens_sel+1}/{self.hyperparameters['n_members']}")

                if use_pretrained:
                    ensemble_member.load_weights(self.pretrained_weights)

                ensemble_member.compile(loss=self.loss, optimizer=self.optimizer, metrics=[self.loss])

                # validate on the spare segment
                if self.hyperparameters['n_segments']!=1:
                    if valX is not None or valy is not None:
                        warnings.warn("Validation data set will be one of the segments. The provided validation data set is not used!")

                    start_ind = j * self.segment_len
                    end_ind = (j+1) *  self.segment_len

                    trainXens = np.delete(trainX, np.s_[start_ind:end_ind], axis=0)
                    trainyens = np.delete(trainy, np.s_[start_ind:end_ind])
                    valXens = trainX[start_ind:end_ind]
                    valyens = trainy[start_ind:end_ind]

                # validate on test data set
                elif self.hyperparameters['n_segments']==1:
                    if valX is None or valy is None:
                        raise MissingArgumentError("When segments length is 1, a validation data set must be provided.")
                    trainXens = trainX
                    trainyens = trainy
                    valXens = valX
                    valyens = valy

                history = ensemble_member.fit(trainXens, trainyens,
                                            epochs=self.hyperparameters['epochs'], batch_size=self.hyperparameters['batch_size'],
                                            verbose=self.hyperparameters['verbose'],
                                            shuffle=True, callbacks=[self.es],
                                            validation_data=(valXens, valyens))

                self.history.append(history)
                self.val_loss.append(ensemble_member.evaluate(valXens, valyens)[1])
                self.ensemble.append(ensemble_member)
                j+=1
            i+=1
        self.mean_val_loss = np.mean(self.val_loss)

        # print computation time
        end_time = time.time()
        passed_time = np.round(end_time-start_time, decimals=1)
        print(f'Computation time: {passed_time}s')


    def fit_RandomizedSearch(self, trainX, trainy,  n_iter=10, **kwargs):

        # check if hyperparameters where provided in lists for randomized search
        if len(self.hyperparameters_search) == 0:
            raise Exception("No variable indicated for hyperparameter search!")

        #iterate with randomized hyperparameters
        best_loss = np.inf
        for i in range(n_iter):
            print_header(f"Search iteration Nr {i+1}/{n_iter}")

            # random selection of hyperparameters
            for key in self.hyperparameters_search.keys():
                low = self.hyperparameters_search[key][0]
                high = self.hyperparameters_search[key][1]

                self.hyperparameters[key] = np.random.uniform(low, high)

            self.fit(trainX, trainy, **kwargs)

            # check if validation score was enhanced
            if self.mean_val_loss<best_loss:
                best_loss = self.mean_val_loss
                self.best_hyperparameters = self.hyperparameters.copy()

                small_print_header("New best hyperparameters")
                print(f"Mean loss: {best_loss}")
                print(self.best_hyperparameters)

        # refit the model with optimized hyperparameter
        # AND to have the weights of the DE for the best hyperparameters again
        print_header("Refit the model with best hyperparamters")

        self.hyperparameters = self.best_hyperparameters.copy()
        print(self.hyperparameters)
        self.fit(trainX, trainy, **kwargs)

        print(f"best loss search: {best_loss}")
        print(f"loss refitting : {self.mean_val_loss}")

    def predict(self, X):
        """
        Generates the ensemble prediction of a model ensemble

        :param model_ens: list of ensemble models
        :param X: The features

        """
        if self.hyperparameters['pdf']=='normal':
            pred_ens = np.zeros((X.shape[0], 2, self.hyperparameters['n_members']))

        elif self.hyperparameters['pdf']=='skewed':
            pred_ens = np.zeros((X.shape[0], 3, self.hyperparameters['n_members']))

        elif self.hyperparameters['pdf'] is None:
            pred_ens = np.zeros((X.shape[0], 1, self.hyperparameters['n_members']))

        for i in range(self.hyperparameters['n_members']):
            pred_ens[:,:,i] = self.ensemble[i].predict(X)
        return self._mixture(pred_ens)


    def _mixture(self, pred):
        """
        returns the ensemble mixture results
        """
        mix_mean = pred[:,0,:].mean(axis=1)

        if self.hyperparameters['pdf']=='normal':
            mix_var = np.mean(pred[:,0,:]**2 + pred[:,1,:]**2, axis=1)  - mix_mean**2
            mix_std = np.sqrt(mix_var)
            return [mix_mean, mix_std]

        elif self.hyperparameters['pdf']=='skewed':
            mix_var = np.mean(pred[:,0,:]**2 + pred[:,1,:]**2, axis=1)  - mix_mean**2
            mix_std = np.sqrt(mix_var)
            print("Mixture prediction for skewed distribution is not ready!")
            return mix_mean, mix_std, None

        elif self.hyperparameters['pdf'] is None:
            return mix_mean



    def evaluate(self, ytrue, mean_pred, std_pred=False):
        """
        Negative - log -likelihood for the prediction of a gaussian probability
        """
        if std_pred is None:
            return rmse(ytrue, mean_pred)

        else:
            mean = mean_pred
            sigma = std_pred + 1e-6 # adding 1-e6 for numerical stability reasons

            first  =  0.5 * np.log(np.square(sigma))
            second =  np.square(mean - ytrue) / (2  * np.square(sigma))
            summed = first + second

            loss =  np.mean(summed, axis=-1)
            return loss

    def save(self, location='', dir_name='ensemble'):
        """
        Save the ensemble
        """
        path = join(location, dir_name)
        if not exists(path):
            mkdir(path)
        else:
            rmtree(path)
            mkdir(path)

        for i in range(self.hyperparameters['n_members']):
            path_h5 = join(path, f"member{i}.h5")
            save_model(self.ensemble[i], path_h5, include_optimizer=False)

    def save_weights(self, location='', dir_name='ensemble'):
        """
        Saves the weights
        """
        path = join(location, dir_name)
        if not exists(path):
            mkdir(path)
        else:
            rmtree(path)
            mkdir(path)

        for i in range(self.hyperparameters['n_members']):
            path_h5 = join(path, f"member{i}.h5")
            self.ensemble[i].save_weights(path_h5)

    def load(self, location=None,  dir_name='dem'):
        """
        Load the ensemble
        """
        if location is None:
            location = getcwd()

        path = join(location, dir_name)
        files = listdir(path)
        self.hyperparameters = {}
        self.hyperparameters['n_members'] = len(files)
        self.ensemble = []

        for file in files:
            file_path = join(path, file)
            self.ensemble.append(load_model(file_path))

        output_neurons = self.ensemble[0].get_output_shape_at(0)[1]

        if output_neurons==2:
            self.hyperparameters['pdf'] = 'normal'

        elif output_neurons==3:
            self.hyperparameters['pdf'] = 'skewed'
        else:
            self.hyperparameters['pdf'] = None

        self.get_model_desc(self.hyperparameters['pdf'])

