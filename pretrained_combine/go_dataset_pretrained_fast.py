import os
import pickle
from torch.utils.data import Dataset
import collections
from transformer_encoder.model import *
from transformer_encoder import data_process


class GoDataset(Dataset):
    '''Class for go dataset'''

    def __init__(self, config, split='train'):
        super(GoDataset, self).__init__()
        self.split = split
        self.data_dir = config['data_dir']
        self.device = config['device']
        self.portion = config['portion']

        self.data = []
        self.vocab_size = None
        self.data_raw = {}
        self.choices = {}

        self.get_board()
        self.get_text()
        self.get_choices()
        self.get_pos_neg_examples()

    def __getitem__(self, index):
        ''' Get the positive and negative examples at index '''
        if isinstance(index, collections.Sequence):
            return tuple(
                (i, self.data[i]) for i in index
            )
        else:
            return index, self.data[index]

    def __len__(self):
        return len(self.data)

    def get_board(self):
        print("------ Loading boards ------")
        pkl_path = os.path.join(self.data_dir, self.split + '_board_inputs.pkl')

        with open(pkl_path, 'rb') as input_file:
            board_data = pickle.load(input_file)
        self.data_raw['bin_input_datas'] = board_data['bin_input_datas']  # 'bin_input_datas': bin_input_datas, 'global_input_datas': global_input_datas
        self.data_raw['global_input_datas'] = board_data['global_input_datas']
        print('Boards shape', self.data_raw['bin_input_datas'] )

    def get_text(self):
        print("------ Loading text ------")
        comments_filepath = os.path.join(self.data_dir,  f'{self.split}_comments.tok.32000.txt')
        vocab_filepath = os.path.join(self.data_dir,  'vocab.32000')
        comments, vocab_size = data_process.read_comment_subword(comments_filepath, vocab_filepath, 5)

        self.data_raw['texts'] = torch.tensor(comments).to(self.device)
        self.vocab_size = vocab_size
        print('Texts shape', self.data_raw['texts'].shape)

    def get_choices(self):
        print("------ Loading choices ------")
        choices_path = os.path.join(self.data_dir, f'{self.split}.choices.pkl')
        with open(choices_path, 'rb') as input_file:
            self.choices = pickle.load(input_file)

    def get_example(self, board_idx, text_idx, label):
        bin_input_datas = self.data_raw['bin_input_datas'][board_idx]
        global_input_datas = self.data_raw['global_input_datas'][board_idx]
        text = self.data_raw['texts'][text_idx]
        return {'bin_input_datas': bin_input_datas, 'global_input_datas': global_input_datas,
                'text': text.to(self.device), 'label': label}

    def get_pos_neg_examples(self):
        print("------ Loading positive and negative examples ------")
        for index in range(int(self.portion * len(self.choices['choice_indices']))):
            choice_indices = self.choices['choice_indices'][index]
            pos_idx = choice_indices[self.choices['answers'][index]]
            neg_idx = choice_indices[1] if self.choices['answers'][index] == 0 else choice_indices[0]

            pos_example = self.get_example(pos_idx, pos_idx, 1)
            neg_example = self.get_example(pos_idx, neg_idx, 0)
            self.data.append(pos_example)
            self.data.append(neg_example)