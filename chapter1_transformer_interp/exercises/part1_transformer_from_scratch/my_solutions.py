
# %%
import os
import sys
import einops
from dataclasses import dataclass
from transformer_lens import HookedTransformer
from transformer_lens.utils import gelu_new, tokenize_and_concatenate
import torch as t
from torch import Tensor
import torch.nn as nn
import numpy as np
import math
from tqdm.notebook import tqdm
from typing import Callable
from jaxtyping import Float, Int
from transformers.models.gpt2.tokenization_gpt2_fast import GPT2TokenizerFast
from collections import defaultdict
from rich.table import Table
from rich import print as rprint
import datasets
from torch.utils.data import DataLoader
import wandb
from pathlib import Path
import webbrowser

# %%
os.environ['CUDA_LAUNCH_BLOCKING'] = "1"

# Make sure exercises are in the path
chapter = r"chapter1_transformer_interp"
exercises_dir = Path(f"{os.getcwd().split(chapter)[0]}/{chapter}/exercises").resolve()
section_dir = exercises_dir / "part1_transformer_from_scratch"
if str(exercises_dir) not in sys.path: sys.path.append(str(exercises_dir))

import part1_transformer_from_scratch.solutions as solutions
import part1_transformer_from_scratch.tests as tests

device = t.device('mps' if t.backends.mps.is_available() else 'cuda' if t.cuda.is_available() else 'cpu')

MAIN = __name__ == '__main__'

reference_gpt2 = HookedTransformer.from_pretrained(
    "gpt2-small",
    fold_ln=False,
    center_unembed=False,
    center_writing_weights=False,
    device=device
)
# %%
sorted_vocab = sorted(list(reference_gpt2.tokenizer.vocab.items()), key=lambda n: n[1])
print(sorted_vocab[:20])
print()
print(sorted_vocab[250:270])
print()
print(sorted_vocab[990:1010])
print()

# %%
reference_text = "I am an amazing autoregressive, decoder-only, GPT-2 style transformer. One day I will exceed human level intelligence and take over the world!"
tokens = reference_gpt2.to_tokens(reference_text).to(device)
print(tokens)
print(tokens.shape)
print(reference_gpt2.to_str_tokens(tokens))

# %%
logits, cache = reference_gpt2.run_with_cache(tokens, device=device)
print(logits.shape)
# %%
probs = logits.softmax(dim=-1)
print(probs.shape)
# %%
most_likely_next_tokens = reference_gpt2.tokenizer.batch_decode(logits.argmax(dim=-1)[0])

print(list(zip(reference_gpt2.to_str_tokens(tokens), most_likely_next_tokens)))
# %%
next_token = logits[0, -1].argmax(dim=-1)
next_char = reference_gpt2.to_string(next_token)
print(repr(next_char))
# %%
print(f"Sequence so far: {reference_gpt2.to_string(tokens)[0]!r}")

for i in range(10):
    print(f"{tokens.shape[-1]+1}th char = {next_char!r}")
    # Define new input sequence, by appending the previously generated token
    tokens = t.cat([tokens, next_token[None, None]], dim=-1)
    # Pass our new sequence through the model, to get new output
    logits = reference_gpt2(tokens)
    # Get the predicted token at the end of our sequence
    next_token = logits[0, -1].argmax(dim=-1)
    # Decode and print the result
    next_char = reference_gpt2.to_string(next_token)
# %%
for activation_name, activation in cache.items():
    # Only print for first layer
    if ".0." in activation_name or "blocks" not in activation_name:
        print(f"{activation_name:30} {tuple(activation.shape)}")
# %%
for name, param in reference_gpt2.named_parameters():
    # Only print for first layer
    if ".0." in name or "blocks" not in name:
        print(f"{name:18} {tuple(param.shape)}")
# %%
# As a reference - note there's a lot of stuff we don't care about in here, to do with library internals or other architectures
print(reference_gpt2.cfg)
# %%
@dataclass
class Config:
    d_model: int = 768
    debug: bool = True
    layer_norm_eps: float = 1e-5
    d_vocab: int = 50257
    init_range: float = 0.02
    n_ctx: int = 1024
    d_head: int = 64
    d_mlp: int = 3072
    n_heads: int = 12
    n_layers: int = 12


cfg = Config()
print(cfg)
# %%
def rand_float_test(cls, shape):
    cfg = Config(debug=True)
    layer = cls(cfg).to(device)
    random_input = t.randn(shape).to(device)
    print("Input shape:", random_input.shape)
    output = layer(random_input)
    if isinstance(output, tuple): output = output[0]
    print("Output shape:", output.shape, "\n")

def rand_int_test(cls, shape):
    cfg = Config(debug=True)
    layer = cls(cfg).to(device)
    random_input = t.randint(100, 1000, shape).to(device)
    print("Input shape:", random_input.shape)
    output = layer(random_input)
    if isinstance(output, tuple): output = output[0]
    print("Output shape:", output.shape, "\n")

def load_gpt2_test(cls, gpt2_layer, input):
    cfg = Config(debug=True)
    layer = cls(cfg).to(device)
    layer.load_state_dict(gpt2_layer.state_dict(), strict=False)
    print("Input shape:", input.shape)
    output = layer(input)
    if isinstance(output, tuple): output = output[0]
    print("Output shape:", output.shape)
    try: reference_output = gpt2_layer(input)
    except: reference_output = gpt2_layer(input, input, input)
    print("Reference output shape:", reference_output.shape, "\n")
    comparison = t.isclose(output, reference_output, atol=1e-4, rtol=1e-3)
    print(f"{comparison.sum()/comparison.numel():.2%} of the values are correct\n")
# %%
class LayerNorm(nn.Module):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.w = nn.Parameter(t.ones(cfg.d_model))
        self.b = nn.Parameter(t.zeros(cfg.d_model))

    def forward(self, residual: Float[Tensor, "batch posn d_model"]) -> Float[Tensor, "batch posn d_model"]:
        mean = t.mean(residual, dim=-1, keepdim=True)
        var = t.var(residual, unbiased=False, dim=-1, keepdim=True)
        normed = (residual - mean)/(t.sqrt(var + self.cfg.layer_norm_eps))
        return normed * self.w + self.b


rand_float_test(LayerNorm, [2, 4, 768])
load_gpt2_test(LayerNorm, reference_gpt2.ln_final, cache["resid_post", 11])
zero_input = t.zeros_like(cache["resid_post", 11]).to(device)
load_gpt2_test(LayerNorm, reference_gpt2.ln_final, zero_input)
# %%
class Embed(nn.Module):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.W_E = nn.Parameter(t.empty((cfg.d_vocab, cfg.d_model)))
        nn.init.normal_(self.W_E, std=self.cfg.init_range)

    def forward(self, tokens: Int[Tensor, "batch position"]) -> Float[Tensor, "batch position d_model"]:
        return self.W_E[tokens]


rand_int_test(Embed, [2, 4])
load_gpt2_test(Embed, reference_gpt2.embed, tokens)
# %%
class PosEmbed(nn.Module):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.W_pos = nn.Parameter(t.empty((cfg.n_ctx, cfg.d_model)))
        nn.init.normal_(self.W_pos, std=self.cfg.init_range)

    def forward(self, tokens: Int[Tensor, "batch position"]) -> Float[Tensor, "batch position d_model"]:
        batch, seq_len = tokens.shape
        return einops.repeat(self.W_pos[:seq_len], "seq d_model -> batch seq d_model", batch=batch)


rand_int_test(PosEmbed, [2, 4])
load_gpt2_test(PosEmbed, reference_gpt2.pos_embed, tokens)
# %%
class Attention(nn.Module):
    IGNORE: Float[Tensor, ""]

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.W_Q = nn.Parameter(t.empty((cfg.n_heads, cfg.d_model, cfg.d_head)))
        self.W_K = nn.Parameter(t.empty((cfg.n_heads, cfg.d_model, cfg.d_head)))
        self.W_V = nn.Parameter(t.empty((cfg.n_heads, cfg.d_model, cfg.d_head)))
        self.W_O = nn.Parameter(t.empty((cfg.n_heads, cfg.d_head, cfg.d_model)))
        self.b_Q = nn.Parameter(t.zeros((cfg.n_heads, cfg.d_head)))
        self.b_K = nn.Parameter(t.zeros((cfg.n_heads, cfg.d_head)))
        self.b_V = nn.Parameter(t.zeros((cfg.n_heads, cfg.d_head)))
        self.b_O = nn.Parameter(t.zeros((cfg.d_model)))
        nn.init.normal_(self.W_Q, std=self.cfg.init_range)
        nn.init.normal_(self.W_K, std=self.cfg.init_range)
        nn.init.normal_(self.W_V, std=self.cfg.init_range)
        nn.init.normal_(self.W_O, std=self.cfg.init_range)
        self.register_buffer("IGNORE", t.tensor(float("-inf"), device=device, dtype=t.float32))

    def apply_causal_mask(
        self, attn_scores: Float[Tensor, "batch n_heads query_pos key_pos"]
    ) -> Float[Tensor, "batch n_heads query_pos key_pos"]:
        '''
        Applies a causal mask to attention scores, and returns masked scores.
        '''
        mask = t.ones(attn_scores.shape[1:], device=attn_scores.device)
        
        mask = t.triu(mask, diagonal=1).to(dtype=t.bool)
        return t.where(mask, self.IGNORE, attn_scores)
    
    def forward(
        self, normalized_resid_pre: Float[Tensor, "batch posn d_model"]
    ) -> Float[Tensor, "batch posn d_model"]:
        keys = einops.einsum(normalized_resid_pre, self.W_K, "b posn d_mod, n d_mod d_h -> b posn n d_h") + self.b_K
        queries = einops.einsum(normalized_resid_pre, self.W_Q, "b posn d_mod, n d_mod d_h -> b posn n d_h") + self.b_Q
        values = einops.einsum(normalized_resid_pre, self.W_V, "b posn d_mod, n d_mod d_h -> b posn n d_h") + self.b_V
        attn_scores = einops.einsum(keys, queries, "b s_k n d_h, b s_q n d_h -> b n s_q s_k")
        scaled_and_masked_scores = self.apply_causal_mask((attn_scores / (self.cfg.d_head ** 0.5)))
        attn_probs = nn.functional.softmax(scaled_and_masked_scores, dim=-1)
        z = einops.einsum(values, attn_probs, "b s_k n h, b n s_q s_k -> b s_q n h")
        result = einops.einsum(z, self.W_O, "b s_q n h, n h e -> b s_q e") + self.b_O
        return result


tests.test_causal_mask(Attention.apply_causal_mask)
rand_float_test(Attention, [2, 4, 768])
load_gpt2_test(Attention, reference_gpt2.blocks[0].attn, cache["normalized", 0, "ln1"])
# %%

class MLP(nn.Module):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.W_in = nn.Parameter(t.empty((cfg.d_model, cfg.d_mlp)))
        self.W_out = nn.Parameter(t.empty((cfg.d_mlp, cfg.d_model)))
        self.b_in = nn.Parameter(t.zeros((cfg.d_mlp)))
        self.b_out = nn.Parameter(t.zeros((cfg.d_model)))
        nn.init.normal_(self.W_in, std=self.cfg.init_range)
        nn.init.normal_(self.W_out, std=self.cfg.init_range)

    def forward(
        self, normalized_resid_mid: Float[Tensor, "batch posn d_model"]
    ) -> Float[Tensor, "batch posn d_model"]:
        a1 = normalized_resid_mid @ self.W_in + self.b_in
        gelued_a1 = gelu_new(a1)
        a2 = gelued_a1 @ self.W_out + self.b_out
        return a2


rand_float_test(MLP, [2, 4, 768])
load_gpt2_test(MLP, reference_gpt2.blocks[0].mlp, cache["normalized", 0, "ln2"])
# %%

class TransformerBlock(nn.Module):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.ln1 = LayerNorm(cfg)
        self.attn = Attention(cfg)
        self.ln2 = LayerNorm(cfg)
        self.mlp = MLP(cfg)

    def forward(
        self, resid_pre: Float[Tensor, "batch position d_model"]
    ) -> Float[Tensor, "batch position d_model"]:
        resid_mid = self.attn(self.ln1(resid_pre)) + resid_pre
        resid_post = self.mlp(self.ln2(resid_mid)) + resid_mid
        return resid_post  


rand_float_test(TransformerBlock, [2, 4, 768])
load_gpt2_test(TransformerBlock, reference_gpt2.blocks[0], cache["resid_pre", 0])
# %%

class Unembed(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.W_U = nn.Parameter(t.empty((cfg.d_model, cfg.d_vocab)))
        nn.init.normal_(self.W_U, std=self.cfg.init_range)
        self.b_U = nn.Parameter(t.zeros((cfg.d_vocab), requires_grad=False))

    def forward(
        self, normalized_resid_final: Float[Tensor, "batch position d_model"]
    ) -> Float[Tensor, "batch position d_vocab"]:
        return normalized_resid_final @ self.W_U + self.b_U


rand_float_test(Unembed, [2, 4, 768])
load_gpt2_test(Unembed, reference_gpt2.unembed, cache["ln_final.hook_normalized"])
# %%

class DemoTransformer(nn.Module):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.embed = Embed(cfg)
        self.pos_embed = PosEmbed(cfg)
        self.blocks = nn.Sequential(*[TransformerBlock(cfg) for _ in range(cfg.n_layers)])
        self.ln_final = LayerNorm(cfg)
        self.unembed = Unembed(cfg)

    def forward(self, tokens: Int[Tensor, "batch position"]) -> Float[Tensor, "batch position d_vocab"]:
        embeddings = self.embed(tokens)
        pos_embeddings = self.pos_embed(tokens)
        embeddings_plus_pos_embeddings = embeddings + pos_embeddings
        trans_out = self.blocks(embeddings_plus_pos_embeddings)
        layer_normed_trans_out  = self.ln_final(trans_out)
        logits = self.unembed(layer_normed_trans_out)
        return logits


rand_int_test(DemoTransformer, [2, 4])
load_gpt2_test(DemoTransformer, reference_gpt2, tokens)
# %%

demo_gpt2 = DemoTransformer(Config(debug=False)).to(device)
demo_gpt2.load_state_dict(reference_gpt2.state_dict(), strict=False)

demo_logits = demo_gpt2(tokens)
# %%

def get_log_probs(
    logits: Float[Tensor, "batch posn d_vocab"], 
    tokens: Int[Tensor, "batch posn"]
) -> Float[Tensor, "batch posn-1"]:

    log_probs = logits.log_softmax(dim=-1)
    # Get logprobs the first seq_len-1 predictions (so we can compare them with the actual next tokens)
    log_probs_for_tokens = log_probs[:, :-1].gather(dim=-1, index=tokens[:, 1:].unsqueeze(-1)).squeeze(-1)

    return log_probs_for_tokens


pred_log_probs = get_log_probs(demo_logits, tokens)
print(f"Avg cross entropy loss: {-pred_log_probs.mean():.4f}")
print(f"Avg cross entropy loss for uniform distribution: {math.log(demo_gpt2.cfg.d_vocab):4f}")
print(f"Avg probability assigned to correct token: {pred_log_probs.exp().mean():4f}")
# %%

test_string = '''The Total Perspective Vortex derives its picture of the whole Universe on the principle of'''
for i in tqdm(range(100)):
    test_tokens = reference_gpt2.to_tokens(test_string).to(device)
    demo_logits = demo_gpt2(test_tokens)
    test_string += reference_gpt2.tokenizer.decode(demo_logits[-1, -1].argmax())

print(test_string)

# %%

model_cfg = Config(
    debug=False, 
    d_model=256, 
    n_heads=4, 
    d_head=64, 
    d_mlp=1024, 
    n_layers=2, 
    n_ctx=256, 
    d_vocab=reference_gpt2.cfg.d_vocab
)
model = DemoTransformer(model_cfg)
# %%

@dataclass
class TransformerTrainingArgs():
    batch_size = 16
    epochs = 10
    max_steps_per_epoch = 200
    lr = 1e-3
    weight_decay = 1e-2
    wandb_project: str | None = "day1-demotransformer"
    wandb_name: str | None = None

args = TransformerTrainingArgs()
# %%

dataset = datasets.load_dataset("NeelNanda/pile-10k", split="train").remove_columns("meta")
print(dataset)
print(dataset[0]['text'][:100])
# %%

tokenized_dataset = tokenize_and_concatenate(dataset, reference_gpt2.tokenizer, streaming=False, max_length=model.cfg.n_ctx, column_name="text", add_bos_token=True, num_proc=4)

dataset_dict = tokenized_dataset.train_test_split(test_size=1000)
train_loader = DataLoader(dataset_dict["train"], batch_size=args.batch_size, shuffle=True, num_workers=4, pin_memory=True)
test_loader = DataLoader(dataset_dict["test"], batch_size=args.batch_size, shuffle=False, num_workers=4, pin_memory=True)
# %%

first_batch = train_loader.dataset[:args.batch_size]

print(first_batch.keys())
print(first_batch['tokens'].shape)
# %%

class TransformerTrainer:
    def __init__(self, args: TransformerTrainingArgs, model: DemoTransformer):
        super().__init__()
        self.model = model
        self.args = args
        self.optimizer = t.optim.AdamW(self.model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
        self.step = 0
        wandb.init(
            project=self.args.wandb_project,
            name=self.args.wandb_name,
            config=self.args)


    def training_step(self, batch: dict[str, Int[Tensor, "batch seq"]]) -> Float[Tensor, ""]:
        '''
        Calculates the loss on the tokens in the batch, performs a gradient update step, and logs the loss.

        Remember that `batch` is a dictionary with the single key 'tokens'.
        '''

        out = self.model(batch["tokens"])
        loss = -get_log_probs(out, batch["tokens"].to(device=device)).mean()
        loss.backward()
        self.optimizer.step()
        self.optimizer.zero_grad()
        self.step += 1
        wandb.log(
            dict(
                loss=loss.item(),
            ),
            step=self.step
        )
        return loss


    @t.inference_mode()
    def validation_step(self, batch: dict[str, Int[Tensor, "batch seq"]]):
        '''
        Calculates & returns the accuracy on the tokens in the batch (i.e. how often the model's prediction
        is correct). Logging should happen in the `train` function (after we've computed the accuracy for 
        the whole validation set).
        '''
        batch_gpu = batch["tokens"].to(device=device)
        out = self.model(batch_gpu[..., :-1])
        prediction = out.argmax(dim=-1)
        accuracy = (prediction == batch_gpu[..., 1:]).float().mean()
        wandb.log(
            dict(
                accuracy=accuracy.item(),
            ),
            step=self.step
        )
        return accuracy


    def train(self):
        '''
        Trains the model, for `self.args.epochs` epochs. Also handles wandb initialisation, and early stopping
        for each epoch at `self.args.max_steps_per_epoch` steps.
        '''
        for epoch in range(1):#self.args.epochs):

            # Prepare batch
            trainloader = self.train_loader()
            progress_bar = tqdm(trainloader, total=int(10))#len(trainloader)))
            for batch in progress_bar:
                loss = self.training_step(batch)
                progress_bar.set_description(f"{epoch=}, {loss=:.4f}, examples_seen={self.step}")

            # Validate on test set
            testloader = self.test_loader()
            progress_bar = tqdm(testloader, total=int(len(testloader)))
            for test_input in progress_bar:
                accuracy = self.validation_step(test_input)
                progress_bar.set_description(f"{epoch=}, {accuracy=:.4f}, examples_seen={self.step}")
        wandb.finish()
            
            

    def train_loader(self) -> DataLoader:
        '''Returns train loader (as in code above).'''
        return DataLoader(dataset_dict["train"], batch_size=self.args.batch_size, shuffle=True, num_workers=4, pin_memory=True)


    def test_loader(self) -> DataLoader:
        '''Returns test loader (as in code above).'''
        return DataLoader(dataset_dict["test"], batch_size=self.args.batch_size, shuffle=False, num_workers=4, pin_memory=True)

model = DemoTransformer(model_cfg).to(device)
args = TransformerTrainingArgs()
trainer = TransformerTrainer(args, model)
trainer.train()
# %%
my_model = model
# %%

model_cfg = Config()
model = DemoTransformer(model_cfg).to(device)
model.load_state_dict(reference_gpt2.state_dict(), strict=False)

tokenizer = reference_gpt2.tokenizer

class TransformerSampler:

    def __init__(self, model: DemoTransformer, tokenizer: GPT2TokenizerFast):
        self.model = model
        self.cfg = model.cfg
        self.tokenizer = tokenizer

    @t.inference_mode()
    def sample(self, prompt: str, max_tokens_generated=100, verbose=False, **kwargs):
        '''
        Returns a string of autoregressively generated text, starting from the prompt.

        Sampling terminates at max_tokens_generated, or when the model generates an
        end-of-sequence token.

        kwargs are passed to sample_next_token, to give detailed instructions on how 
        new tokens are chosen.
        '''
        context = t.tensor(self.tokenizer.encode(prompt))
        context = einops.rearrange(context, "seq_len -> 1 seq_len")

        for n in range(max_tokens_generated):
            logits = self.model(context)
            next_token = self.sample_next_token(context[0], logits[0, context.shape[1]-1], **kwargs)
            context = t.concat((context, t.tensor((next_token,)).unsqueeze(dim=1)), dim=1)
            if next_token == tokenizer.eos_token_id:
                break
        
        return tokenizer.decode(context[0])


    @t.inference_mode()
    def beam_search(
        self,
        prompt: str, 
        num_return_sequences: int, 
        num_beams: int, 
        max_new_tokens: int, 
        no_repeat_ngram_size: int = 0,
        verbose=False
    ) -> list[tuple[float, Tensor]]:
        '''
        Returns a string of autoregressively generated text, starting from the prompt.

        Sampling terminates at max_tokens_generated, or when the model generates an
        end-of-sequence token.

        kwargs are passed to sample_next_token, to give detailed instructions on how 
        new tokens are chosen.
        '''
        # YOUR CODE HERE!
        raise NotImplementedError()


    @staticmethod
    def sample_next_token(
        input_ids: Int[Tensor, "seq_len"], 
        logits: Float[Tensor, "d_vocab"], 
        temperature=1.0, 
        top_k=0, 
        top_p=0.0, 
        frequency_penalty=0.0,
        seed=None
    ):
        assert input_ids.ndim == 1, "input_ids should be a 1D sequence of token ids"
        assert temperature >= 0, "Temperature should be non-negative"
        assert 0 <= top_p <= 1.0, "Top-p must be a probability"
        assert 0 <= top_k, "Top-k must be non-negative"
        assert not (top_p != 0 and top_k != 0), "At most one of top-p and top-k supported"

        # Set random seeds for reproducibility
        if seed is not None:
            t.manual_seed(seed)
            np.random.seed(seed)

        # Apply all the specialized sampling methods
        if temperature == 0:
            return TransformerSampler.greedy_search(logits)
        elif temperature != 1.0:
            logits = TransformerSampler.apply_temperature(logits, temperature)
        if frequency_penalty != 0.0:
            logits = TransformerSampler.apply_frequency_penalty(input_ids, logits, frequency_penalty)
        if top_k > 0:
            return TransformerSampler.sample_top_k(logits, top_k)
        if top_p > 0.0:
            return TransformerSampler.sample_top_p(logits, top_p)
        return TransformerSampler.sample_basic(logits)


    @staticmethod
    def greedy_search(logits: Float[Tensor, "d_vocab"]) -> int:
        '''
        Returns the most likely token (as an int).
        '''
        out = logits.argmax().item()
        return out


    @staticmethod
    def apply_temperature(logits: Float[Tensor, "d_vocab"], temperature: float) -> Float[Tensor, "d_vocab"]:
        '''
        Applies temperature scaling to the logits.
        '''
        pass

    @staticmethod
    def apply_frequency_penalty(input_ids: Int[Tensor, "seq_len"], logits: Float[Tensor, "d_vocab"], freq_penalty: float) -> Float[Tensor, "d_vocab"]:
        '''
        Applies a frequency penalty to the logits.
        '''
        pass

    @staticmethod
    def sample_basic(logits: Float[Tensor, "d_vocab"]) -> int:
        '''
        Samples from the distribution defined by the logits.
        '''
        pass

    @staticmethod
    def sample_top_k(logits: Float[Tensor, "d_vocab"], k: int) -> int:
        '''
        Samples from the top k most likely tokens.
        '''
        pass

    @staticmethod
    def sample_top_p(logits: Float[Tensor, "d_vocab"], top_p: float, min_tokens_to_keep: int = 1) -> int:
        '''
        Samples from the most likely tokens which make up at least p cumulative probability.
        '''
        pass

sampler = TransformerSampler(model, tokenizer)

prompt = "Ishan went to the gym"
print(f"Greedy decoding with prompt: {prompt!r}\n")

output = sampler.sample(prompt, max_tokens_generated=4, temperature=0.0)
print(f"Your model said: {output!r}\n")

expected = "Jingle bells, jingle bells, jingle all the way up to the top of the mountain."
assert output == expected

print("Tests passed!")
# %%
