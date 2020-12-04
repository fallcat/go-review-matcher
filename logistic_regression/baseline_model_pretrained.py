import sys
sys.path.append('.')
sys.path.append('..')
from os import listdir
from os.path import isfile, join
import random
import pickle as pkl
from tqdm import tqdm
import numpy as np
import argparse
import time
import random
from itertools import islice, product
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import accuracy_score, precision_score,recall_score, f1_score, fbeta_score, confusion_matrix, roc_curve, auc, classification_report
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.feature_extraction import DictVectorizer
import tensorflow as tf
import katago
from transformer_encoder import get_comment_features
from transformer_encoder.model import *
from transformer_encoder import data_process
import os
os.environ['CUDA_LAUNCH_BLOCKING'] = "1"
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
import nltk
import warnings
warnings.filterwarnings('ignore')
nltk.download('stopwords') 
nltk.download('punkt')
## TODO: Try glove or pymagnitude word embedding, sum the average of the word embeddings
## TODO: Try pretrained text embeddings from transformer encoder

## argparser
parser = argparse.ArgumentParser(description='Processing list of files...')
parser.add_argument('-notes', required=True, help='run id notes to be printed out at the top of the argparser to help distinguish from other runs.')
parser.add_argument('-outDir', required=True, help='directory where output files will be written to')
parser.add_argument('-dataDir', required=True, help='directory where data files will be read in from')
args = parser.parse_args()

## global variables
outdir, dataDir = args.outDir, args.dataDir
train_fnames = sorted([join(dataDir, f) for f in listdir(dataDir) if 'train' in f])
val_fnames = sorted([join(dataDir, f) for f in listdir(dataDir) if 'val' in f])
test_fnames = sorted([join(dataDir, f) for f in listdir(dataDir) if 'test' in f])
vocab_fnames = sorted([join(dataDir, f) for f in listdir(dataDir) if 'vocab' in f])
stones_dict = {'b':0,'w':1}

## sanity checks
print('\n---argparser---:')
for arg in vars(args):
	print(arg, getattr(args, arg), '\t', type(arg))

print('\n---train fnames---')
print(f'len: {len(train_fnames)}')
for f in train_fnames:
	print(f)

print('\n---val fnames---')
print(f'len: {len(val_fnames)}')
for f in val_fnames:
	print(f)

print('\n---test fnames---')
print(f'len: {len(test_fnames)}')
for f in test_fnames:
	print(f)

print('\n---vocab fnames---')
print(f'len: {len(vocab_fnames)}')
for f in vocab_fnames:
	print(f)
print('\n')

## data filenames
train_boards_fname, train_text_fname, train_choices_fname, train_choices_pkl_fname = train_fnames[2], train_fnames[3], train_fnames[1], train_fnames[0]
val_boards_fname, val_text_fname, val_choices_fname, val_choices_pkl_fname = val_fnames[2], val_fnames[3], val_fnames[1], val_fnames[0]
test_boards_fname, test_text_fname, test_choices_fname, test_choices_pkl_fname = test_fnames[2], test_fnames[3], test_fnames[1], test_fnames[0]
vocab_fname = vocab_fnames[0]


def create_pretrained_board_feature_matrix(session, model, fname):

	## I might need to further split the transform data, not sure
	## TODO: Find a go board embedding (find someone that's trained alpha go - mapping from board to stone)

	start = time.time()
	temp = []
	# dict_keys(['boards', 'steps'])
	X = DictVectorizer(dtype=np.float32, sparse=False) ## default np.float64
	data = next(lazy_pickle_load(fname)) 
	for i, board in enumerate(data):
		try:	
			board_arr, color = board[3], board[2]
			# print(f'board_idx: {i}\tboard_arr: {board_arr}\ttype(board_arr): {type(board_arr)}')
			katago_board = katago.extract_features(session, model, board_arr, color) ## katago_board['trunk'] is <class 'numpy.ndarray'> shape (19,19,256)
		except:
			print(e)
			print(f'board_idx: {i}\tboard_arr: {board_arr}\ttype(board_arr): {type(board_arr)}')
			print(f'type(kata')
			print('ending script...')
			exit()

		# katago_board dict keys: dict_keys(['policy0', 'policy1', 'value', 'scoremean', 'scorestdev', 'lead', 'vtime', 'ownership', 'scoring', 'futurepos', 'seki', 'seki2', 'scorebelief', 'sbscale', 'genmove_result', 'trunk'])
		flattened_katago_board = np.mean(katago_board['trunk'],axis=2).flatten() ## flattened_katago_board.shape: (361,) vs. full version (92416,)
		# print(f'flattened_katago_board.shape: {flattened_katago_board.shape}')
		temp.append(dict(zip(range(len(flattened_katago_board)),flattened_katago_board)))
	X.fit(temp)
	X_nparr = X.transform(temp)

	feature_time = time.time() - start
	print(f'board_feature_matrix.shape: {X_nparr.shape}')
	print('Time elapsed making board feature matrix:\t%s' % (time.strftime("%H:%M:%S", time.gmtime(feature_time))))

	return X_nparr


def create_pretrained_text_feature_matrix(choices_pkl_fname, text_fname, vocab_fname, cutoff=5):

	start = time.time()

	comments, labels, vocab_size = prepare_comment(choices_pkl_fname, text_fname, vocab_fname, cutoff)
	comments = comments.to(device)
	print(f'type(comments): {type(comments)}')
	print(f'comments.shape: {comments.shape}')
	exit()

	matrix = CountVectorizer(dtype=np.float32, max_features=1000)
	data = next(lazy_load(fname))
	sentences = [sent.strip() for sent in data]
	X = matrix.fit_transform(sentences).toarray() ## transforms sentences to unigram features

	text_time = time.time() - start
	print(f'text_feature_matrix.shape: {X.shape}')
	print('Time elapsed making text feature matrix:\t%s' % (time.strftime("%H:%M:%S", time.gmtime(text_time))))

	return X

def get_examples(boards_mats, text_mats, fnames):

	start = time.time()

	X, y = [],[]

	for boards_mat, text_mat, fname in zip(boards_mats, text_mats,fnames):
		print(f'boards_mat.shape: {boards_mat.shape}')
		print(f'len(text_mat): {len(text_mat)}')
		print(f'cur fname: {fname}\n')
		choices = next(lazy_load(fname))
		for line in choices:
			indices_str, pos_idx = line.split('\t')
			cur_indices = [int(idx) for idx in indices_str.split()]
			del cur_indices[int(pos_idx)]
			## append positive example
			X.append(np.concatenate((boards_mat[int(pos_idx)],text_mat[int(pos_idx)])))
			y.append(1)
			## append negative example, select the 1st negative example from the group
			X.append(np.concatenate((boards_mat[int(pos_idx)],text_mat[cur_indices[0]])))
			y.append(0)

	examples_time = time.time() - start
	X_nparr, y_nparr = np.array(X), np.array(y)
	print(f'X num_examples: {X_nparr.shape}\ty num_examples: {y_nparr.shape}')
	print('Time elapsed getting examples:\t%s' % (time.strftime("%H:%M:%S", time.gmtime(examples_time))))

	return X_nparr, y_nparr

def automatic_grid_search(X, y, X_test, y_test, test_set=False):

	# GRID SEARCH
	#The newton-cg and lbfgs solvers support only L2 regularization with primal formulation. 
	#The liblinear solver supports both L1 and L2 regularization, with a dual formulation only for the L2 penalty.
	print(f'starting auto parameter search..')
	start = time.time()
	clf = None
	# parameters = [{'penalty': ['l1'], 'solver':['liblinear'], 'C': [0.001,0.01,0.1,1,10]},
	# {'penalty': ['l2'], 'solver':['lbfgs','liblinear','sag'], 'C': [0.001,0.01,0.1,1,10]},
	# {'penalty': ['elasticnet'], 'l1_ratio':[0.25, 0.5, 0.6],'solver':['saga'], 'C': [0.001,0.01,0.1,1,10]}]

	# parameters = [{'penalty': ['l1'], 'solver':['liblinear'], 'C': [0.001,0.01,0.1,1,10]}]
	# parameters = [{'penalty': ['l2'], 'solver':['lbfgs','liblinear','sag'], 'C': [0.001,0.01,0.1,1,10]}] 
	# parameters = [{'penalty': ['elasticnet'], 'l1_ratio':[0.25, 0.5, 0.6],'solver':['saga'], 'C': [0.001,0.01,0.1,1,10]}]
	parameters = {'C': [0.001,0.01,0.1]}

	if test_set:

		scores = ['precision', 'recall', 'f1','accuracy']

		for score in scores:
			print("\n# Tuning hyper-parameters for %s" % score)
			print('\n')

			clf = GridSearchCV(LogisticRegression(random_state=0, max_iter=10000), parameters, scoring='%s_macro' % score)
			clf.fit(X, y)

			print("Best parameters set found on development set:")
			print('\n')
			print(clf.best_params_)
			print('\n')
			print("Grid scores on development set:")
			print('\n')
			means = clf.cv_results_['mean_test_score']
			stds = clf.cv_results_['std_test_score']
			for mean, std, params in zip(means, stds, clf.cv_results_['params']):
				print("%0.3f (+/-%0.03f) for %r"
					  % (mean, std * 2, params))
			print('\n')

			print("Detailed classification report:")
			print('\n')
			print("The model is trained on the full development set.")
			print("The scores are computed on the full evaluation set.")
			print('\n')
			y_true, y_pred = y_test, clf.predict(X_test)
			print(classification_report(y_true, y_pred))
			print('\n')

	else:

		clf = GridSearchCV(LogisticRegression(random_state=0, max_iter=10000), parameters)
		clf.fit(X, y)


	parameter_search_time = time.time() - start
	print(f'end auto parameter search..')
	print('Time elapsed in doing an automatic parameter search:\t%s\n' % (time.strftime("%H:%M:%S", time.gmtime(parameter_search_time))))

	return clf.score(X_test,y_test), clf.best_params_, clf.best_estimator_, clf.best_score_

################
### HELPER FUNCS
################

def progress_in_batches(name, iterator, total_length, increment):
    count = 0
    while True:
        next_batch = list(islice(iterator, increment))
        if len(next_batch) > 0:
            count += len(next_batch)
            print('\nCreating SQLiteDict {}... percentage processed {}'.format(name, (count/total_length)*100))
            yield next_batch
        else:
            break

def lazy_pickle_load(fname):
	file_obj = open(fname, "rb")
	contents = pkl.load(file_obj)['boards']
	file_obj.close()
	yield contents

def lazy_load(fname):
	file_obj = open(fname,"r+")
	contents = file_obj.readlines()
	file_obj.close()
	yield contents


if __name__ == '__main__':

	start = time.time()

	saved_model_dir = "katago/trained_models/g170e-b20c256x2-s5303129600-d1228401921/saved_model/"
	model, model_variables_prefix, model_config_json = katago.get_model(saved_model_dir)

	saver = tf.train.Saver(
		max_to_keep=10000,
		save_relative_paths=True,
	)

	tf.compat.v1.disable_eager_execution()

	with tf.Session() as session:
		saver.restore(session, model_variables_prefix)

		print('\n---TRAIN EXAMPLES---')
		train_board_feature_matrix = create_pretrained_board_feature_matrix(session, model, train_boards_fname) ## 'numpy.ndarray', <class 'sklearn.feature_extraction._dict_vectorizer.DictVectorizer'>
		train_text_feature_matrix  = create_pretrained_text_feature_matrix(train_choices_pkl_fname, train_text_fname, vocab_fname) ## <class 'numpy.ndarray'>
		X_train, y_train = get_examples([train_board_feature_matrix], [train_text_feature_matrix], [train_choices_fname]) ##<class 'numpy.ndarray'>, <class 'numpy.ndarray'>

		print('\n---VALIDATION EXAMPLES---')
		val_board_feature_matrix = create_pretrained_board_feature_matrix(session, model, val_boards_fname)
		val_text_feature_matrix  = create_pretrained_text_feature_matrix(val_choices_pkl_fname, val_text_fname, vocab_fname)
		X_val,  y_val = get_examples([val_board_feature_matrix], [val_text_feature_matrix], [val_choices_fname])

		print('\n---TEST EXAMPLES---')
		test_board_feature_matrix = create_pretrained_board_feature_matrix(session, model, test_boards_fname)
		test_text_feature_matrix  = create_pretrained_text_feature_matrix(test_choices_pkl_fname, test_text_fname, vocab_fname)
		X_test,  y_test = get_examples([test_board_feature_matrix], [test_text_feature_matrix], [test_choices_fname])

		print('\n---TRAIN+VALIDATION COMBINED EXAMPLES FOR AUTOGRID SEARCH---')
		X_comb, y_comb = get_examples([train_board_feature_matrix,val_board_feature_matrix], [train_text_feature_matrix,val_text_feature_matrix], [train_choices_fname,val_choices_fname])

		print('\n---Logistic Regression Auto Grid In Progress---')
		# train_accuracy, train_best_params, train_best_estimator, train_best_score  = automatic_grid_search(X_train[:2000], y_train[:2000], X_train, y_train)
		# val_accuracy, val_best_params, val_best_estimator, val_best_score  = automatic_grid_search(X_train[:2000], y_train[:2000], X_val, y_val)
		test_accuracy, test_best_params, test_best_estimator, test_best_score  = automatic_grid_search(X_comb[:100], y_comb[:100], X_test, y_test, True)
		print(f'test_accuracy: {test_accuracy}\ttest_best_score: {test_best_score}')

		## display results
		print('\n---Results---')
		for title, params, acc in zip(['*test*'], [test_best_params],[test_accuracy]):
			print(f'{title}\tbest_model: {params}\taccuracy: {acc}')
	
	main_time = time.time() - start
	print('Time elapsed in main:\t%s' % (time.strftime("%H:%M:%S", time.gmtime(main_time))))




