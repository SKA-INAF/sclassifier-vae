#!/usr/bin/env python

from __future__ import print_function

##################################################
###    SET SEED FOR REPRODUCIBILITY (DEBUG)
##################################################
#from numpy.random import seed
#seed(1)
#import tensorflow
#tensorflow.random.set_seed(2)

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
import ast

## COMMAND-LINE ARG MODULES
import getopt
import argparse
import collections

## MODULES
from sclassifier import __version__, __date__
from sclassifier import logger
from sclassifier.utils import Utils
from sclassifier.feature_extractor_umap import FeatExtractorUMAP

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
	parser.add_argument('-datalist_key','--datalist_key', dest='datalist_key', required=False, type=str, default="data", help='Dictionary key name to be read in input datalist (default=data)') 
	parser.add_argument('-selcols','--selcols', dest='selcols', required=False, type=str, default='', help='Data column ids to be selected from input data, separated by commas') 

	# - Pre-processing options
	parser.add_argument('--normalize', dest='normalize', action='store_true',help='Normalize feature data in range [0,1] before applying models (default=false)')	
	parser.set_defaults(normalize=False)
	parser.add_argument('-scalerfile', '--scalerfile', dest='scalerfile', required=False, type=str, default='', action='store',help='Load and use data transform stored in this file (.sav)')
	
	parser.add_argument('--classid_label_map', dest='classid_label_map', required=False, type=str, default='', help='Class ID label dictionary')
	parser.add_argument('--objids_excluded_in_train', dest='objids_excluded_in_train', required=False, type=str, default='-1,0', help='Source ids not included for training as considered unknown classes')

	# - UMAP classifier options
	parser.add_argument('-modelfile_umap', '--modelfile_umap', dest='modelfile_umap', required=False, type=str, action='store',help='UMAP model filename (.h5)')
	parser.add_argument('--predict', dest='predict', action='store_true',help='Only predict data according to loaded UMAP model (default=false)')	
	parser.set_defaults(predict=False)
	parser.add_argument('-latentdim_umap', '--latentdim_umap', dest='latentdim_umap', required=False, type=int, default=2, action='store',help='Encoded data dim in UMAP (default=2)')
	parser.add_argument('-mindist_umap', '--mindist_umap', dest='mindist_umap', required=False, type=float, default=0.1, action='store',help='Min dist UMAP par (default=0.1)')
	parser.add_argument('-nneighbors_umap', '--nneighbors_umap', dest='nneighbors_umap', required=False, type=int, default=15, action='store',help='N neighbors UMAP par (default=15)')
	
	parser.add_argument('--run_supervised', dest='run_supervised', action='store_true',help='Run also supervised UMAP over labelled data (if available) (default=false)')	
	parser.set_defaults(run_supervised=False)
	
	# - Save options
	parser.add_argument('-outfile_umap_unsupervised', '--outfile_umap_unsupervised', dest='outfile_umap_unsupervised', required=False, type=str, default='latent_data_umap_unsupervised.dat', action='store',help='Name of UMAP encoded data output file')
	parser.add_argument('-outfile_umap_supervised', '--outfile_umap_supervised', dest='outfile_umap_supervised', required=False, type=str, default='latent_data_umap_supervised.dat', action='store',help='Name of UMAP output file with encoded data produced using supervised method')
	parser.add_argument('-outfile_umap_preclassified', '--outfile_umap_preclassified', dest='outfile_umap_preclassified', required=False, type=str, default='latent_data_umap_preclass.dat', action='store',help='Name of UMAP output file with encoded data produced from pre-classified data')
	parser.add_argument('-outfile_umap_unsupervised_json', '--outfile_umap_unsupervised_json', dest='outfile_umap_unsupervised_json', required=False, type=str, default='latent_data_umap_unsupervised.json', action='store',help='Name of UMAP encoded data json output file')
	parser.add_argument('--save_labels_in_ascii', dest='save_labels_in_ascii', action='store_true',help='Save class labels to ascii (default=save classids)')
	parser.set_defaults(save_labels_in_ascii=False)
	
	parser.add_argument('--no_save_ascii', dest='no_save_ascii', action='store_true',help='Do not save output data to ascii (default=false)')	
	parser.set_defaults(no_save_ascii=False)
	parser.add_argument('--no_save_json', dest='no_save_json', action='store_true',help='Do not save output data to json (default=false)')	
	parser.set_defaults(no_save_json=False)
	parser.add_argument('--no_save_model', dest='no_save_model', action='store_true',help='Do not save model (default=false)')	
	parser.set_defaults(no_save_model=False)

	# - Plot options
	parser.add_argument('--draw', dest='draw', action='store_true',help='Draw plots (default=false)')	
	parser.set_defaults(draw=False)

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
	datalist_key=args.datalist_key
	selcols= []
	if args.selcols!="":
		selcols= [int(x.strip()) for x in args.selcols.split(',')]

	# - Data pre-processing
	normalize= args.normalize
	scalerfile= args.scalerfile
	
	classid_label_map= {}
	if args.classid_label_map!="":
		try:
			classid_label_map= ast.literal_eval(args.classid_label_map)
		except Exception as e:
			logger.error("Failed to convert classid label map string to dict (err=%s)!" % (str(e)))
			return -1	
		
		print("== classid_label_map ==")
		print(classid_label_map)
		
	objids_excluded_in_train= [int(x) for x in args.objids_excluded_in_train.split(',')]	

	# - UMAP options
	latentdim_umap= args.latentdim_umap
	mindist_umap= args.mindist_umap
	nneighbors_umap= args.nneighbors_umap
	modelfile_umap= args.modelfile_umap
	predict= args.predict
	run_supervised= args.run_supervised

	# - Draw options
	draw= args.draw
	
	# - Save options
	no_save_ascii= args.no_save_ascii
	no_save_json= args.no_save_json
	no_save_model= args.no_save_model
	outfile_umap_unsupervised= args.outfile_umap_unsupervised
	outfile_umap_supervised= args.outfile_umap_supervised
	outfile_umap_preclassified= args.outfile_umap_preclassified
	outfile_umap_unsupervised_json= args.outfile_umap_unsupervised_json
	save_labels_in_ascii= args.save_labels_in_ascii

	#===========================
	#==   READ FEATURE DATA
	#===========================
	#ret= Utils.read_feature_data(inputfile)
	#if not ret:
	#	logger.error("Failed to read data from file %s!" % (inputfile))
	#	return 1

	#data= ret[0]
	#snames= ret[1]
	#classids= ret[2]

	#==============================
	#==   RUN UMAP
	#==============================
	umap_class= FeatExtractorUMAP()
	umap_class.selcols= selcols
	umap_class.normalize= normalize
	umap_class.set_encoded_data_unsupervised_outfile(outfile_umap_unsupervised)
	umap_class.set_encoded_data_supervised_outfile(outfile_umap_supervised)
	umap_class.set_encoded_data_preclassified_outfile(outfile_umap_preclassified)
	umap_class.set_encoded_data_unsupervised_json_outfile(outfile_umap_unsupervised_json)
	umap_class.set_encoded_data_dim(latentdim_umap)
	umap_class.set_min_dist(mindist_umap)
	umap_class.set_n_neighbors(nneighbors_umap)
	umap_class.draw= draw
	
	umap_class.classid_label_map= classid_label_map
	umap_class.excluded_objids_train = objids_excluded_in_train
	umap_class.save_labels_in_ascii= save_labels_in_ascii
	umap_class.run_supervised= run_supervised
	umap_class.save_ascii= False if no_save_ascii else True
	umap_class.save_json= False if no_save_json else True
	umap_class.save_model= False if no_save_model else True

	status= 0
	if predict:
		logger.info("Running UMAP classifier prediction using modelfile %s on input feature data ..." % (modelfile_umap))
		#if umap_class.run_predict(data, class_ids=classids, snames=snames, modelfile=modelfile_umap, scalerfile=scalerfile)<0:
		if umap_class.run_predict_from_file(inputfile, modelfile=modelfile_umap, scalerfile=scalerfile, datalist_key=datalist_key)<0:
			logger.error("UMAP prediction failed!")
			return 1
	else:
		logger.info("Running UMAP classifier training on input feature data ...")
		#if umap_class.run_train(data, class_ids=classids, snames=snames, scalerfile=scalerfile)<0:
		if umap_class.run_train_from_file(inputfile, modelfile='', scalerfile=scalerfile, datalist_key=datalist_key)<0:
			logger.error("UMAP training failed!")
			return 1

	return 0

###################
##   MAIN EXEC   ##
###################
if __name__ == "__main__":
	sys.exit(main())

