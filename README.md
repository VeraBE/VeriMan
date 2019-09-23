# VeriMan

With VeriMan you can define temporal properties using your contract's variables, and Solidity's numeric and boolean operations. Then, the tool instruments the contract to find a trace that falsifies at least one of the properties or prove that they hold. You can then check the instrumented contract against any tool that tries to make asserts fail, like Mythril, or any tool that also attemps to proove they hold.

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

VeriMan also allows you to directly use VeriSol and Manticore for the analysis. It runs the instrumented contract on VeriSol, if a counterexample is found then it executes it on Manticore to get a concrete transaction sequence. Right now there's a compatibility issue for this feature because VeriSol supports Solidity 0.5.10 and Manticore requires a version lower than 0.5, so your contract has to be compatible with both to run this analysis.

Echidna is also supported, if you set `for_echidna` to `true` in your configuration file, VeriMan will generate a contract ready to be fuzzed with it.

## Requirements
 
* Python3
* [`npm install -g sol-merger`](https://www.npmjs.com/package/sol-merger)
* `pip install -r requirements.txt`
* [VeriSol](https://github.com/microsoft/verisol/tree/0fd7f14956a24ad2b931a9a441f012d53daab609) if you want to use the verification feature.

## Usage

* Copy `config_example.json` into `config.json` and update values, you can define the properties there.
* `python3 client.py`

## Big TODOs

* Handle inheritance
* Support return values of functions on predicates
* Support more Solidity constructs (`ether`, `finney`, `wei`, `minutes`, `hours`, `days`, etc.)