import matplotlib.pyplot as plt
from ninolearn.IO.read_processed import data_reader
from ninolearn.plot.nino_timeseries import nino_background
from ninolearn.utils import scale
from scipy.stats import spearmanr
from sklearn import linear_model

import numpy as np
import pandas as pd

def spearman_lag(x,y, max_lags=80):
    scorr = np.zeros(max_lags)
    scorr[0] = spearmanr(x[:], y[:])[0]
    for i in np.arange(1, max_lags):
        scorr[i] = spearmanr(x[i:], y[:-i])[0]

    return scorr

def pearson_lag(x,y, max_lags=80):
    pcorr = np.zeros(max_lags)
    pcorr[0] = np.corrcoef(x[:], y[:])[0,1]
    for i in np.arange(1, max_lags):
        pcorr[i] = np.corrcoef(x[i:], y[:-i])[0,1]

    return pcorr

def residual(x, y):
    p = np.polyfit(x, y, deg=1)
    ylin = p[0] + p[1] * x
    yres = y - ylin
    return yres

def basin_means(data, lat1=2.5, lat2=-2.5):
    data_basin =  data.loc[dict(lat=slice(lat1, lat2), lon=slice(120, 240))]
    data_basin_mean = data_basin.mean(dim='lat', skipna=True).mean(dim='lon', skipna=True)

    data_WP = data.loc[dict(lat=slice(lat1, lat2), lon=slice(120, 160))]
    data_WP_mean = data_WP.mean(dim='lat', skipna=True).max(dim='lon', skipna=True)

    data_CP = data.loc[dict(lat=slice(lat1, lat2), lon=slice(160, 210))]
    data_CP_mean = data_CP.mean(dim='lat', skipna=True).mean(dim='lon', skipna=True)

    data_EP = data.loc[dict(lat=slice(lat1, lat2), lon=slice(180, 240))]
    data_EP_mean = data_EP.mean(dim='lat', skipna=True).mean(dim='lon', skipna=True)

    return data_basin_mean, data_WP_mean, data_CP_mean, data_EP_mean

plt.close("all")

reader = data_reader(startdate='1980-01', enddate='2017-12', lon_min=30)
oni = reader.read_csv('oni')
nino34 = reader.read_csv('nino3.4M')
nino12 = reader.read_csv('nino1+2M')
nino4 = reader.read_csv('nino4M')
nino3 = reader.read_csv('nino3M')

iod = reader.read_csv('iod')
#wwvwest = reader.read_csv('wwvwest')
wwv = reader.read_csv('wwv_proxy')
wp_edge = reader.read_csv('wp_edge', processed='total')

#wwv_total = reader.read_csv('wwv', processed='Volume')
#GODAS data

taux = reader.read_netcdf('taux', dataset='NCEP', processed='anom')

taux_basin_mean, taux_WP_mean, taux_CP_mean, taux_EP_mean = basin_means(taux, lat1=7.5, lat2=-7.5)


X = nino4.values.reshape(-1, 1)
y = taux_WP_mean.values
reg = linear_model.LinearRegression(fit_intercept=True)

reg.fit(X , y)
#%%
taux_sst = reg.predict(X)
taux_WP_mean.values = taux_WP_mean.values - taux_sst

sst = reader.read_netcdf('sst', dataset='ERSSTv5', processed='anom')
olr = reader.read_netcdf('olr', dataset='NCAR', processed='anom')
olr_basin_mean, olr_WP_mean, olr_CP_mean, olr_EP_mean = basin_means(olr, lat1=-2.5, lat2=7.5)


#taux_CP_mean = taux_CP_mean.rolling(time=3).mean()
#ucur = reader.read_netcdf('ucur', dataset='GODAS', processed='anom')
#ucur_basin_mean, ucur_WP_mean, ucur_CP_mean, ucur_EP_mean = basin_means(ucur, lat1=-2.5, lat2=5.5)
#
#ucur_basin_mean_roll = ucur_basin_mean.rolling(time=24, center=False).mean()
#ucur_EP_mean = pd.Series(data=ucur_EP_mean, index=ucur_WP_mean.time.values)


#ssh = reader.read_netcdf('sshg', dataset='GODAS', processed='anom')
#ssh = reader.read_netcdf('sshg', dataset='GODAS', processed='anom')
#ssh_grad = np.sort(np.gradient(ssh.loc[dict(lat=0, lon=slice(200,280))],axis=1),axis=1)

#ssh_grad = np.nanmean(np.gradient(ssh.loc[dict(lat=0, lon=slice(210, 240))],axis=1),axis=1)
#ssh_grad = pd.Series(data=ssh_grad, index=ssh.time.values)

#kiri=ssh.loc[dict(lat=0, lon=197.5)]

#%%


#network = reader.read_statistic('network_metrics', variable='sshg',
#                           dataset='GODAS', processed="anom")

network = reader.read_statistic('network_metrics', variable='zos',
                           dataset='ORAS4', processed="anom")

#pca_dechca = reader.read_statistic('pca', variable='dec_hca', dataset='NODC', processed='anom')
pca_decsst = reader.read_statistic('pca', variable='dec_sst', dataset='ERSSTv5', processed='anom')
pca_decsst = pca_decsst['pca1']

c2 = network['fraction_clusters_size_2']
#c3 = network['fraction_clusters_size_3']
#c5 = network['fraction_clusters_size_5']
#S = network['fraction_giant_component']
H = network['corrected_hamming_distance']
#T = network['global_transitivity']
#C = network['avelocal_transmissivity']
#L = network['average_path_length']
#rho = network['edge_density']

#c2_oras = network2['fraction_clusters_size_2']

plt.subplots()
var = scale(pca_decsst)
var2 = scale(wwv)
#var3 = scale(wwvwest)
nino = scale(nino34)
nino3norm = scale(nino3)
nino4norm = scale(nino4)


var.plot(c='r')
nino.plot(c='k')
var2.plot(c='b')
#var3.plot(c='g')

#%%
plt.subplots()
plt.vlines(12,-1,1, colors="grey")
plt.vlines(6,-1,1, colors="grey")
plt.vlines(0,-1,1, colors="grey")
#plt.xcorr(nino, var3, maxlags=80, color="r", label="EP", usevlines=False)
#plt.xcorr(nino, var2, maxlags=80, color="b", label="CP", usevlines=False)
plt.xcorr(nino, var, maxlags=80, label="WP", usevlines=False)
plt.hlines(0,-1000,1000)
plt.ylim(-1,1)
plt.xlim(0,48)
plt.legend()
plt.xlabel('lag month')

#%%
"""
Archieved


##%% =============================================================================
## GFDL
## =============================================================================
#reader = data_reader(startdate='1701-01', enddate='2199-12')
#
#nino34gfdl = reader.read_csv('nino3.4M_gfdl')
#iodgfdl = reader.read_csv('iod_gfdl')
#network = reader.read_statistic('network_metrics', variable='tos',
#                           dataset='GFDL-CM3', processed="anom")
#
#pca = reader.read_statistic('pca', variable='tas',
#                           dataset='GFDL-CM3', processed="anom")
#
#c2 = network['fraction_clusters_size_2']
#c3 = network['fraction_clusters_size_3']
#c5 = network['fraction_clusters_size_5']
#S = network['fraction_giant_component']
#H = network['corrected_hamming_distance']
#T = network['global_transitivity']
#C = network['avelocal_transmissivity']
#L = network['average_path_length']
#
#pca2 = pca['pca2']
#
#plt.subplots()
#var = scale(C)
#nino = scale(nino34gfdl)
#
#var.plot(c='r')
#nino.plot(c='k')
#
#plt.subplots()
#plt.xcorr(nino, var, maxlags=80)
#plt.vlines(12,-1,1, colors="r")
#plt.vlines(6,-1,1, colors="b")
#plt.vlines(0,-1,1, colors="k")
#plt.ylim(-1,1)
"""