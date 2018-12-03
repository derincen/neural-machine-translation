# from https://pytorch.org/tutorials/intermediate/seq2seq_translation_tutorial.html

# from https://pytorch.org/tutorials/intermediate/seq2seq_translation_tutorial.html

class RNNencoder(nn.Module):
    def __init__(self,
                 vocab_size=len(zhen_zh_train_token2id), # for chinese
                 embedding_size=300,
                 percent_dropout=0.3, 
                 hidden_size=256,
                 num_gru_layers=4,
                 max_sentence_len=350):
        
        super(RNNencoder, self).__init__()
        
        self.hidden_size = hidden_size
        self.num_layers = num_gru_layers
        
        self.vocab_size = vocab_size
        self.embed_size = embedding_size
        self.dropout = percent_dropout
        self.embed_source = nn.Embedding(self.vocab_size,
                                         self.embed_size,
                                         padding_idx=0
                                        )
        
        self.max_sentence_len = max_sentence_len
        
        self.GRU = nn.GRU(self.embed_size, 
                          self.hidden_size, 
                          self.num_layers, 
                          batch_first=True, 
                          bidirectional=False)
        
        self.drop_out_function = nn.Dropout(self.dropout)
        
    def init_hidden(self, batch_size):
        
        hidden_ = torch.zeros(self.num_layers*self.num_directions, 
                             batch_size, self.hidden_size).to(device)
        return hidden_

    def forward(self, source_sentence, source_mask, source_lengths):
        """Returns source lengths to feed into the decoder, since we do not want
        the translation length to be above/below a certain treshold*source sentence length."""
        
        sort_original_source = sorted(range(len(source_lengths)), 
                             key=lambda sentence: -source_lengths[sentence])
        unsort_to_original_source = sorted(range(len(source_lengths)), 
                             key=lambda sentence: sort_original_source[sentence])
        
        source_sentence = source_sentence[sort_original_source]
        _source_mask = source_mask[sort_original_source]
        source_lengths = source_lengths[sort_original_source]
        batch_size, seq_len_source = source_sentence.size()
        
        # init hidden
        if self.GRU.bidirectional:
            self.num_directions = 2
        else:
            self.num_directions = 1
        
        self.hidden_source = self.init_hidden(batch_size)
        # (self.num_layers*self.num_directions, batch_size, self.hidden_size)
        # (1, 32, 256)
        # https://pytorch.org/docs/stable/nn.html
        # print ("self hidden size. = "+str(self.hidden_source.size()))
        
        # If batch_first == True, then the input and output tensors are provided as 
        # (batch_size, seq_len, feature)
        # https://pytorch.org/docs/stable/nn.html
        # print ("seq len source = "+str(seq_len_source))
        embeds_source = self.embed_source(source_sentence).view(batch_size, seq_len_source,
                                                               self.embed_size)
        
        # print ("embeds source size = "+str(embeds_source.size()))
        
        embeds_source = source_mask*embeds_source + (1-_source_mask)*embeds_source.clone().detach()
        
        embeds_source = torch.nn.utils.rnn.pack_padded_sequence(embeds_source, 
                                                                source_lengths, 
                                                                batch_first=True)
        
        gru_out_source, self.hidden_source = self.GRU(embeds_source, self.hidden_source)
        
        # ref: pytorch documentation
        # hidden source : h_n of shape 
        # (num_layers * num_directions, batch_size, hidden_size)
        # print ("hidden source size = "+str(self.hidden_source.size()))
        
        # ref: pytorch documentation
        # Like output, the layers can be separated using 
        # h_n.view(num_layers, num_directions, batch_size, hidden_size)
        hidden_source = self.hidden_source.view(self.num_layers, self.num_directions, 
                                                batch_size, self.hidden_size)
        # the following should print (1, 1, 32, 256) for this config
        # print ("hidden source size after view = "+str(hidden_source.size()))
        
        # get the mean along 0th axis (over layers)
        hidden_source = torch.mean(hidden_source, dim=0) ## mean instead of sum for source representation as suggested in the class
        # the following should print (1, 32, 256)
        # print ("hidden source size after mean = "+str(hidden_source.size()))
        
        if self.GRU.bidirectional:
            hidden_source = torch.cat([hidden_source[:,i,:] for i in range(self.num_directions)], dim=1)
            gru_out_source = gru_out_source
        else:
            hidden_source = hidden_source
            gru_out_source = gru_out_source
            
        # view before unsort
        hidden_source = hidden_source.view(batch_size, self.hidden_size)
        
        # the following should print (32, 256)
        # print("hidden source size before unsort = "+str(hidden_source.size()))
        # UNSORT HIDDEN
        hidden_source = hidden_source[unsort_to_original_source] ## back to original indices
        
        gru_out_source, _ = torch.nn.utils.rnn.pad_packed_sequence(gru_out_source,
                                                                  batch_first=True)
        
        source_lengths = source_lengths[unsort_to_original_source]

        return hidden_source, source_lengths


class RNNdecoder(nn.Module):
    def __init__(self,
                 vocab_size=len(zhen_en_train_token2id), # for chinese-english's english
                 embedding_size=300,
                 percent_dropout=0.3, 
                 hidden_size=256,
                 num_gru_layers=1,
                 max_sentence_len=300):
        
        super(RNNdecoder, self).__init__()
        self.vocab_size = vocab_size
        self.embed_size = embedding_size
        self.dropout = percent_dropout
        self.max_sentence_len = max_sentence_len

        self.hidden_size = hidden_size
        self.num_layers = num_gru_layers
        
        self.GRU = nn.GRU(self.embed_size, 
                          self.hidden_size, 
                          self.num_layers, 
                          batch_first=True, 
                          bidirectional=False)
        
        self.GRUcell = nn.GRUCell(self.embed_size, 
                          self.hidden_size)
        
        self.ReLU = nn.ReLU
        
        self.drop_out_function = nn.Dropout(self.dropout)
        
        self.embed_target = nn.Embedding(self.vocab_size,
                                         self.embed_size, padding_idx=0)
        
        self.sigmoid = nn.Sigmoid()
        
        # *2 because we are concating hidden with embedding plus context
        self.linear_layer = nn.Linear(self.hidden_size*2, self.vocab_size)
        self.log_softmax = nn.LogSoftmax(dim=0)
        self.softmax = nn.Softmax(dim=0)
        
    def init_hidden(self, batch_size):
        hidden = torch.zeros(self.num_layers, 
                             batch_size, self.hidden_size).to(device)
        
        return hidden

    def forward(self,
                decoder_hidden, ## decoder_hidden = encoder_hidden at first time_step
                input_, # input
                target_lengths,
                target_mask,
                time_step):
        
        # input (batch_size, seq_len_target = 1)
        # hidden (self.num_layers*self.num_directions, batch_size, self.hidden_size)
        
        self.input = input_
        print ("self.input size = "+str(self.input.size()))
        
        sort_original_target = sorted(range(len(target_lengths)), 
                             key=lambda sentence: -target_lengths[sentence])
        unsort_to_original_target = sorted(range(len(target_lengths)), 
                             key=lambda sentence: sort_original_target[sentence])
        
        self.input = self.input[sort_original_target]
        _target_mask = target_mask[sort_original_target]
        target_lengths = target_lengths[sort_original_target]
        
        # seq_len_target is always 1 in the decoder since we are 
        # passing the tokens for only 1 time_step at a time
        batch_size, seq_len_target = self.input.size()
        
        if self.GRU.bidirectional:
            self.num_directions = 2
        else:
            self.num_directions = 1
        
        # hidden => initial hidden will be the same as the context
        # vector, which is the hidden_source tensor
        # then as we update the hidden state at each time step, this will be 
        # updated as well
        self.hidden = decoder_hidden.view(self.num_layers*self.num_directions,
                                          batch_size, self.hidden_size)
        
        # the following should print (1, 32, 256) for this config
        print ("self.hidden size = "+str(self.hidden.size()))
        
        self.input = self.input.unsqueeze(1)
        
        embeds_target = self.drop_out_function(self.embed_target(self.input.long())).view(batch_size,
                                                                                   seq_len_target,
                                                                                   -1)
    
#         embeds_target = target_mask*embeds_target + (1-_target_mask)*embeds_target.clone().detach()
        embeds_target = target_mask[:,time_step,:].unsqueeze(1)*embeds_target + \
                        (1-_target_mask[:,time_step,:].unsqueeze(1))*embeds_target.clone().detach()

        print ("embeds_target size = "+str(embeds_target.size()))    
        
#         embeds_target = torch.nn.utils.rnn.pack_padded_sequence(embeds_target,
#                                                         target_lengths,
#                                                         batch_first=True)
        
#         print ("type embeds target = "+str(type(embeds_target)))

        gru_out_target, self.hidden = self.GRU(embeds_target.data.view(batch_size, 1, self.embed_size),
                                               self.hidden)
        
        # ref: pytorch documentation
        # hidden source : h_n of shape 
        # (num_layers * num_directions, batch_size, hidden_size)
        # the following should print (1, 32, 256) for this config
        print ("hidden size after GRU = "+str(self.hidden.size()))
        
        # undo packing 
#         gru_out_target, _ = torch.nn.utils.rnn.pad_packed_sequence(gru_out_target,
#                                                                    batch_first=True)
        
#         print ("out size after GRU = "+str(gru_out_target.size()))


        hidden = self.hidden.view(self.num_layers, self.num_directions,
                                  batch_size, self.hidden_size)
        hidden = torch.sum(hidden, dim=0) # we don't divide here, just sum
    
        print ("hidden size = "+str(hidden.size()))
        
        if self.GRU.bidirectional:
            # separate layers
            gru_out_target = gru_out_target.contiguous().view(seq_len_target,
                                                              batch_size,
                                                              self.num_directions,
                                                              self.hidden_size)
        else:
            gru_out_target = gru_out_target
        
        print ("gru out size = "+str(gru_out_target.size()))
        
        # sum along sequence
        gru_out_target = torch.sum(gru_out_target, dim=1) # we don't divide here, just sum
        
        if self.GRU.bidirectional:
            hidden = torch.cat([hidden[:,i,:] for i in range(self.num_directions)], 
                               dim=0)
            gru_out_target = torch.cat([gru_out_target[:,i,:] for i in range(self.num_directions)], 
                                       dim=1)
        else:
            hidden = hidden.view(batch_size, 
                                 self.num_directions, self.hidden_size)
            gru_out_target = gru_out_target.view(batch_size,
                                                 self.num_directions, self.hidden_size)
        
        hidden = hidden[unsort_to_original_target] ## back to original indices
        gru_out_target = gru_out_target[unsort_to_original_target] ## back to original indices

        gru_out_target = self.sigmoid(gru_out_target)
        # concating embedding + context = gru_out_target with hidden
        out = torch.cat([gru_out_target,hidden], dim=2)
        
#         print ("out size after concat = "+str(out.size()))
        
        out = self.linear_layer(out)
        
        # softmax over vocabulary
        pred = self.log_softmax(out)

        return pred, hidden


def convert_to_softmax(tensor_of_indices,
                      vocab_size = len(zhen_en_train_token2id)):
    """
    - tensor_of_indices: tensor of size (batch_size)
    
    Returns: tensor of size (batch_size x vocab size) that
             represents the softmax over vocabulary for the true tokens
             at each timestep for each sentence in the batch."""
    
#     inp = torch.LongTensor(1, 32) % 100
    index_tensor_ = torch.unsqueeze(tensor_of_indices, 2)

    one_hot = torch.FloatTensor(1, 32, vocab_size).zero_()
    one_hot.scatter_(2, index_tensor_, 1)
    
    return one_hot

class Translate(nn.Module):
    def __init__(self, encoder, decoder):
        super().__init__()
        
        self.encoder = encoder
        self.decoder = decoder
        
    def forward(self, source_sentence, target_sentence, 
                source_mask, target_mask, source_lengths,
                target_lengths):

        # to hold previously decoded ys
        y_outputs = torch.zeros(batch_size, 
                                target_sentence.size(1), 
                                len(zhen_en_train_token2id)).to(device)
        
        #last hidden state of the encoder is the context
        encoder_hidden, source_lengths = self.encoder(source_sentence,
                                               source_mask,
                                               source_lengths)
        
#         print ("context size = "+str(context.size()))
#         print ("context (hidden source) = "+str(context))

        # context also used as the initial hidden state of the decoder
        decoder_hidden = encoder_hidden

        # # decoder should start with SOS tokens 
        # ref: https://pytorch.org/tutorials/intermediate/seq2seq_translation_tutorial.html
        input_ = SOS_token*torch.ones(batch_size,1).view(-1,1)
        # print ("input size = "+str(input_.size()))
#         print ("input = "+str(input))
        
        for t in range(0, target_sentence.size(1)):
            
            decoder_out, decoder_hidden = self.decoder(decoder_hidden, # = gru_out_source - instead of encoded_source[0]
                                                 input_, # instead of target sentence up to t 
                                                 target_lengths,  # target lengths
                                                 target_mask,
                                                 t)
            
#             print ("decoder out size = "+str(decoder_out.size()))
            for s in range(batch_size):
                y_outputs[s,t] = decoder_out[s,0]
#             print ("y_outputs size = "+str(y_outputs.size()))
#             print ("decoder out = "+str(decoder_out))
#             print ("decoder out size = "+str(decoder_out.size()))
#             print ("decoder_out[s,0] = "+str(decoder_out[s,0]))

            token_out = torch.max(decoder_out.view(batch_size,self.decoder.vocab_size),1)[1]
#             print ("token out size = "+str(token_out.size()))
#             print ("token out at time step t = "+str(token_out))
            input_ = token_out.view(-1,1)
            
        return y_outputs


BATCH_SIZE = 32

def train(model, loader=zhen_train_loader,criterion=loss_function,
          optimizer=None, 
          epoch=None):
    
    model.train()
    
    epoch_loss = 0
    
    for batch_idx, (source_sentence, source_mask, source_lengths, 
                    target_sentence, target_mask, target_lengths)\
    in enumerate(loader):
        
        source_sentence, source_mask = source_sentence.to(device), source_mask.to(device),  
        target_sentence, target_mask = target_sentence.to(device), target_mask.to(device),
        
        optimizer.zero_grad()
        
        # output softmax as generated by decoder 
        output = model(source_sentence, target_sentence, 
                source_mask, target_mask, source_lengths,
                target_lengths)
        
        print ("output size = "+str(output.size()))
        
        batch_target = torch.zeros(batch_size,model.decoder.embed_size)
        for i in range(target_sentence.size(0)):
            one_hot_ = convert_to_softmax(target_sentence[i])
            batch_target[i] = one_hot_
            
        print ("batch_target[ix] sum = "+str(torch.sum(batch_target[0],1)))

        loss = criterion(out, target)
        print ("loss = "+str(loss))
        
        loss.backward()
        
        torch.nn.utils.clip_grad_norm_(model.parameters(), clip)
        
        optimizer.step()
        
        epoch_loss += loss.item()
        
    return epoch_loss/BATCH_SIZE


num_epochs = 10
lr = 1e-4
# batch_

loss_train = []

for epoch in range(num_epochs):
    print ("epoch = "+str(epoch))

    loss = train(model,
                       loader = zhen_train_loader,
                       optimizer = torch.optim.Adam(model.parameters(), 
                                                   lr=lr),
                      epoch = epoch)
    
    loss_train.append(loss)
    
    print (loss_train)