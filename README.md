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
- [x] **T** `num_calls >= 0` (up to loops == 100)
- [x] **F** `a_called -> b_called`
- [x] **F** `previously(!a_called) && a_called`
- [x] **T** `previously(num_calls >= 0) && (num_calls >= 0)` (up to loops == 10)
- [x] **F** `since(num_calls > 0, a_called)`
- [x] **T** `since(num_calls >= 0, a_called)` (up to loops == 5)
- [ ] **F** `once(num_calls == 2)`
- [ ] **T** `once(num_calls == -1)`
- [ ] **F** `always(num_calls > 0)`
- [ ] **T** `always(num_calls >= 0)`