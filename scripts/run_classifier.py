#!/usr/bin/env python

from __future__ import print_function

##################################################
###          MODULE IMPORT
##################################################
## STANDARD MODULES
import os
import sys
import subprocess
import string
import time
import signal
from threading import Thread
import datetime
import numpy as np
import random
import math
import logging

## COMMAND-LINE ARG MODULES
import getopt
import argparse
import collections

## MODULES
from sclassifier_vae import __version__, __date__
from sclassifier_vae import logger
from sclassifier_vae.data_loader import DataLoader
from sclassifier_vae.utils import Utils
from sclassifier_vae.classifier import SClassifier


import matplotlib.pyplot as plt

#### GET SCRIPT ARGS ####
def str2bool(v):
	if v.lower() in ('yes', 'true', 't', 'y', '1'):
		return True
	elif v.lower() in ('no', 'false', 'f', 'n', '0'):
		return False
	else:
		raise argparse.ArgumentTypeError('Boolean value expected.')

###########################
##     ARGS
###########################
def get_args():
	"""This function parses and return arguments passed in"""
	parser = argparse.ArgumentParser(description="Parse args.")

	# - Input options
	parser.add_argument('-inputfile','--inputfile', dest='inputfile', required=True, type=str, help='Input feature data table filename') 
	parser.add_argument('-inputfile_cv','--inputfile_cv', dest='inputfile_cv', type=str, default='', help='Input feature validation data table filename') 
	
	# - Pre-processing options
	parser.add_argument('--normalize', dest='normalize', action='store_true',help='Normalize feature data in range [0,1] before applying models (default=false)')	
	parser.set_defaults(normalize=False)
	parser.add_argument('-scalerfile', '--scalerfile', dest='scalerfile', required=False, type=str, default='', action='store',help='Load and use data transform stored in this file (.sav)')
	
	# - Model options
	parser.add_argument('-classifier','--classifier', dest='classifier', required=False, type=str, default='DecisionTreeClassifier', help='Classifier to be used.') 
	parser.add_argument('-modelfile', '--modelfile', dest='modelfile', required=False, type=str, default='', action='store',help='Classifier model filename (.sav)')
	parser.add_argument('--predict', dest='predict', action='store_true',help='Predict model on input data (default=false)')	
	parser.set_defaults(predict=False)
	parser.add_argument('--binary_class', dest='binary_class', action='store_true',help='Perform a binary classification {0=EGAL,1=GAL} (default=multiclass)')	
	parser.set_defaults(binary_class=False)
	parser.add_argument('--balance_classes', dest='balance_classes', action='store_true',help='Apply class weights to balance classes (default=false)')	
	parser.set_defaults(balance_classes=False)

	# - Tree options
	parser.add_argument('-max_depth','--max_depth', dest='max_depth', required=False, type=int, default=None, help='Max depth for decision tree, random forest and LGBM')
	parser.add_argument('-min_samples_split','--min_samples_split', dest='min_samples_split', required=False, type=int, default=2, help='Minimum number of samples required to split an internal node')
	parser.add_argument('-min_samples_leaf','--min_samples_leaf', dest='min_samples_leaf', required=False, type=int, default=1, help='Minimum number of samples required to be at a leaf node')
	parser.add_argument('-n_estimators','--n_estimators', dest='n_estimators', required=False, type=int, default=100, help='Number of boosted or forest trees to fit') 
	parser.add_argument('-num_leaves','--num_leaves', dest='num_leaves', required=False, type=int, default=31, help='Max number of leaves in one tree for LGBM classifier') 
	parser.add_argument('-learning_rate','--learning_rate', dest='learning_rate', required=False, type=float, default=0.1, help='Learning rate for LGBM classifier and others (TBD)') 
	parser.add_argument('-niters','--niters', dest='niters', required=False, type=int, default=100, help='Number of boosting iterations for LGBM classifier and others (TBD)') 
	
	# - Run option
	parser.add_argument('--run_scan', dest='run_scan', action='store_true',help='Run LGBM scan (default=false)')	
	parser.set_defaults(run_scan=False)
	parser.add_argument('-ntrials','--ntrials', dest='ntrials', required=False, type=int, default=1, help='Number of Optuna study trials (default=1)') 
	
	# - Output options
	parser.add_argument('-outfile','--outfile', dest='outfile', required=False, type=str, default='classified_data.dat', help='Output filename (.dat) with classified data') 

	args = parser.parse_args()	

	return args



##############
##   MAIN   ##
##############
def main():
	"""Main function"""

	#===========================
	#==   PARSE ARGS
	#===========================
	logger.info("Get script args ...")
	try:
		args= get_args()
	except Exception as ex:
		logger.error("Failed to get and parse options (err=%s)",str(ex))
		return 1

	# - Input filelist
	inputfile= args.inputfile
	inputfile_cv= args.inputfile_cv

	# - Data pre-processing
	normalize= args.normalize
	scalerfile= args.scalerfile

	# - Model options
	classifier= args.classifier
	modelfile= args.modelfile
	predict= args.predict
	multiclass= True
	if args.binary_class:
		multiclass= False

	balance_classes= args.balance_classes

	# - Tree options
	max_depth= args.max_depth
	min_samples_split= args.min_samples_split
	min_samples_leaf= args.min_samples_leaf
	n_estimators= args.n_estimators
	num_leaves= args.num_leaves
	learning_rate= args.learning_rate
	niters= args.niters

	# - Run options
	run_scan= args.run_scan
	ntrials= args.ntrials
	
	# - Output options
	outfile= args.outfile

	#===========================
	#==   READ FEATURE DATA
	#===========================
	ret= Utils.read_feature_data(inputfile)
	if not ret:
		logger.error("Failed to read data from file %s!" % (inputfile))
		return 1

	data= ret[0]
	snames= ret[1]
	classids= ret[2]

	#====================================
	#==   READ FEATURE VALIDATION DATA
	#====================================
	data_cv= None
	snames_cv= []
	classids_cv= []

	if inputfile_cv!="":
		ret_cv= Utils.read_feature_data(inputfile_cv)
		if not ret_cv:
			logger.error("Failed to read validation data from file %s!" % (inputfile_cv))
			return 1

		data_cv= ret_cv[0]
		snames_cv= ret_cv[1]
		classids_cv= ret_cv[2]

	#===========================
	#==   CLASSIFY DATA
	#===========================
	logger.info("Running classifier on input feature data ...")
	sclass= SClassifier(multiclass=multiclass)
	sclass.normalize= normalize
	sclass.classifier= classifier
	sclass.outfile= outfile
	sclass.max_depth= max_depth
	sclass.min_samples_split= min_samples_split
	sclass.min_samples_leaf= min_samples_leaf
	sclass.n_estimators= n_estimators
	sclass.num_leaves= num_leaves
	sclass.learning_rate= learning_rate
	sclass.niters= niters
	sclass.balance_classes= balance_classes

	if predict:
		status= sclass.run_predict(
			data, classids, snames, 
			modelfile, scalerfile
		)
	else:
		if run_scan:
			status= sclass.run_lgbm_scan(n_trials=ntrials)

		else:
			status= sclass.run_train(
				data, classids, snames, 
				modelfile, scalerfile,
				data_cv, classids_cv, snames_cv,
			)
	
	if status<0:
		logger.error("Classifier run failed!")
		return 1
	

	return 0

###################
##   MAIN EXEC   ##
###################
if __name__ == "__main__":
	sys.exit(main())

