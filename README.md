# VeriMan

With VeriMan you can define temporal properties using your contract's variables, and
Solidity's numeric and boolean operations.

The tool instruments the contract to find a trace that falsifies at least one of the properties.
To do so, it runs the instrumented contract against VeriSol, if it finds a trace then it executes
it on Manticore to get a concrete trasaction sequence.

Its possible to only enable the instrumentation option to get a contract that can be run
against any tool that tries to make asserts fail, like Mythril.

For example, given the following contract:

```
contract Example {
    bool public a_called = false;
    bool public b_called = false;
    bool public c_called = false;
    int public num_calls = 0;

    function a() public {
        a_called = true;
        num_calls++;
    }

    function b() public {
        require(a_called);
        
        b_called = true;
        num_calls++;
    }

    function c() public {
        require(a_called);
        require(b_called);

        c_called = true;
        num_calls++;
    }
}
```

You could define as temporal properties:

* `b_called -> a_called`, where `->` is a classical "implies"
* `previously(num_calls >= 0) && (num_calls >= 0)`, where `previously` refers to the previous state
* `since(num_calls > 0, a_called)`, where `since(p, q)` is interpreted as "in the transaction sequence executed,
`q` was true at least once, and since then `p` was always true"
* `a_called -> once(num_calls > 0)`, where `once(p)` represents "`p` was true at least one time in the
transaction sequence"
* `always(num_calls >= 0)`, with the interpretation of `always` you can imagine :relaxed:

## Usage

* Copy `config_example.py` into `config.py` and update values, you can define the properties there.
* `python veriman.py`

## Requirements
 
* [`npm install -g sol-merger`](https://www.npmjs.com/package/sol-merger)
* `pip install requirements.txt`
* [`VeriSol`](https://github.com/microsoft/verisol/tree/e5a245f63ee8ab5d12ff4524f35d52bc56ea825d)

## Big TODOs

* Report which predicates failed
* Handle inheritance
* Support return values of functions on predicates
* Support more Solidity constructs (`ether`, `finney`, `wei`, `minutes`, `hours`, `days`, etc.)
* Support Echidna