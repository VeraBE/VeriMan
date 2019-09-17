# VeriMan

## Usage

* Copy `config_example.py` into `config.py` and update values
* `python veriman.py`

## Requirements
 
* `npm install -g sol-merger`
* `pip install requirements.txt`
* [`VeriSol`](https://github.com/microsoft/verisol)

## Tests

Temporarily documenting here properties and its results, proper tests are needed.

#### InOrderHard

- [x] **F** `num_calls > 0`
- [x] **T** `num_calls >= 0` (up to bound)
- [x] **F** `a_called -> b_called`
- [x] **F** `a_called -> (b_called && previously(c_called))`
- [x] **F** `previously(!a_called) && a_called`
- [x] **T** `previously(num_calls >= 0) && (num_calls >= 0)` (up to bound)
- [x] **F** `since(num_calls > 0, a_called)`
- [x] **T** `since(num_calls >= 0, a_called)` (up to bound)
- [x] **F** `once(num_calls == 2)` (1)
- [x] **T** `a_called -> once(num_calls > 0)` (up to bound)  (2)
- [x] **F** `always(num_calls > 0)`
- [x] **T** `always(num_calls >= 0)` (up to bound)

(1) Intuitively, it should hold, because it does in a specific transaction sequence,
but VeriMan only allows you to check properties at the transaction sequence level, not at the contract
state level. It's true that once in the history of the contract num_calls can be 2 at
least one time, but it's doesn't hold in every valid transaction sequence.

(2) After a_called we are completely certain that num_calls > 0 at least once because num_calls
is incremented at the end of every public function, so this property is only false in the initial state
(that we don't check yet, it needs a fix), but in the rest it holds. Finding this depends on the tool
used to analyze the instrumented contract.