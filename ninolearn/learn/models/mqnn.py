import numpy as np

import keras.backend as K
from keras.models import Model, save_model, load_model
from keras.layers import Dense, Input, Add, Subtract, Concatenate
from keras.layers import Dropout, GaussianNoise
from keras.optimizers import Adam
from keras.callbacks import EarlyStopping
from keras import regularizers

from os.path import join, exists
from os import mkdir, listdir, getcwd
from shutil import rmtree

from ninolearn.learn.models.baseModel import baseModel
from ninolearn.learn.losses import tilted_loss_multi
from ninolearn.utils import small_print_header
from ninolearn.exceptions import MissingArgumentError

import warnings

import time

class mqnn(baseModel):
    """

    """
    def __del__(self):
        K.clear_session()

    def __init__(self, q=[0.01, 0.5, 0.99], layers=1, neurons=16, dropout=0.2, noise_in=0.1,
                       noise_out=0.1,
                       l1_hidden=0.1, l2_hidden=0.1,
                       l1_out=0.0, l2_out=0.1,
                       batch_size=10, n_segments=5, n_members_segment=1,
                       lr=0.001, patience = 10, epochs=300, verbose=0,
                       activation='tanh',
                       name='mqnn'):

        self.set_hyperparameters(layers=layers, neurons=neurons, dropout=dropout,
                                 noise_in=noise_in, noise_out=noise_out,
                                 l1_hidden=l1_hidden, l2_hidden=l2_hidden,
                                 l1_out=l1_out, l2_out=l2_out,
                                 activation=activation,
                                 batch_size=batch_size, n_segments=n_segments, n_members_segment=n_members_segment,
                                 lr=lr, patience=patience, epochs=epochs, verbose=verbose,
                                 name=name)
        self.q = q

        def tilted_q_loss(y_true, y_pred):
            return tilted_loss_multi(q, y_true, y_pred)

        self.loss = tilted_q_loss
        self.loss_name = 'tilted_q_loss'

        self.n_outputs = len(q)
        self.output_names = [f'quantile{i}' for i in q]


    def build_model(self, n_features):
        """
        The method builds a new member of the ensemble and returns it.
        """
        # derived parameters
        self.hyperparameters['n_members'] = self.hyperparameters['n_segments'] * self.hyperparameters['n_members_segment']

        # initialize optimizer and early stopping
        self.optimizer = Adam(lr=self.hyperparameters['lr'], beta_1=0.9, beta_2=0.999, epsilon=None, decay=0., amsgrad=False)
        self.es = EarlyStopping(monitor=f'val_{self.loss_name}', min_delta=0.0, patience=self.hyperparameters['patience'], verbose=1,
                   mode='min', restore_best_weights=True)

        inputs = Input(shape=(n_features,))
        h = GaussianNoise(self.hyperparameters['noise_in'],
                          name='noise_input')(inputs)

        for i in range(self.hyperparameters['layers']):

            h = Dense(self.hyperparameters['neurons'], activation=self.hyperparameters['activation'],
                      kernel_regularizer=regularizers.l1_l2(self.hyperparameters['l1_hidden'],
                                                            self.hyperparameters['l2_hidden']),
                      kernel_initializer='random_uniform',
                      bias_initializer='random_uniform',
                      name=f'hidden_{i}')(h)

            h = Dropout(self.hyperparameters['dropout'],
                        name=f'hidden_dropout_{i}')(h)

        median = Dense(1, activation='linear',
                   kernel_regularizer=regularizers.l1_l2(self.hyperparameters['l1_out'],
                                                         self.hyperparameters['l2_out']),
                   kernel_initializer='random_uniform',
                   bias_initializer='random_uniform',
                   name='median')(h)

        qp1 = Dense(1, activation='relu',
                   kernel_regularizer=regularizers.l1_l2(self.hyperparameters['l1_out'],
                                                         self.hyperparameters['l2_out']),
                   kernel_initializer='random_uniform',
                   bias_initializer='random_uniform',
                   name='qp1')(h)

        qp2 = Dense(1, activation='relu',
                   kernel_regularizer=regularizers.l1_l2(self.hyperparameters['l1_out'],
                                                         self.hyperparameters['l2_out']),
                   kernel_initializer='random_uniform',
                   bias_initializer='random_uniform',
                   name='qp2')(h)

        qm1 = Dense(1, activation='relu',
                   kernel_regularizer=regularizers.l1_l2(self.hyperparameters['l1_out'],
                                                         self.hyperparameters['l2_out']),
                   kernel_initializer='random_uniform',
                   bias_initializer='random_uniform',
                   name='qm1')(h)

        qm2 = Dense(1, activation='relu',
                   kernel_regularizer=regularizers.l1_l2(self.hyperparameters['l1_out'],
                                                      self.hyperparameters['l2_out']),
                   kernel_initializer='random_uniform',
                   bias_initializer='random_uniform',
                   name='qm2')(h)


        qp1 = Add()([median, qp1])
        qp2 = Add()([qp1, qp2])
        qm1 = Subtract()([median, qm1])
        qm2 = Subtract()([qm1, qm2])

        out =  Concatenate()([qm2, qm1, median, qp1, qp2])

        out = GaussianNoise(self.hyperparameters['noise_out'],
                           name='noise_out')(out)

        model = Model(inputs=inputs, outputs=out)
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
                                            epochs=self.hyperparameters['epochs'],
                                            batch_size=self.hyperparameters['batch_size'],
                                            verbose=self.hyperparameters['verbose'],
                                            shuffle=True, callbacks=[self.es],
                                            validation_data=(valXens, valyens))

                self.history.append(history)
                self.val_loss.append(ensemble_member.evaluate(valXens, valyens)[1])
                self.ensemble.append(ensemble_member)
                j+=1
            i+=1
        self.mean_val_loss = np.mean(self.val_loss)

        print(f'Loss: {self.mean_val_loss}')
        # print computation time
        end_time = time.time()
        passed_time = np.round(end_time-start_time, decimals=1)
        print(f'Computation time: {passed_time}s')

    def predict(self, X):
        """
        Generates the ensemble prediction of a model ensemble

        :param model_ens: list of ensemble models
        :param X: The features

        """

        pred_ens = np.zeros((X.shape[0], self.n_outputs , self.hyperparameters['n_members']))

        for i in range(self.hyperparameters['n_members']):
            pred_ens[:,:,i] = self.ensemble[i].predict(X)
        return self._mixture(pred_ens)


    def _mixture(self, pred):
        """
        returns the ensemble mixture results
        """
        mix_mean = pred.mean(axis=2)
        return mix_mean.T


    def evaluate(self, ytrue, mean_pred, std_pred=False):
        """
        Negative - log -likelihood for the prediction of a gaussian probability
        """
        pass

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