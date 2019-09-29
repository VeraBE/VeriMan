pragma solidity ^0.5.10;

contract A {
    uint public a_var;

    modifier aModifier() {
        _;
    }

    function aFunction() public aModifier {
        a_var++;
    }

    function toBeOverwritten() public {
        a_var++;
    }
}

contract B {
    uint public b_var;

    function bFunction(int aValue, int anotherValue, bytes memory moreValues, address payable ohNoMoreValues) public returns(int, int) {
        b_var++;

        return (aValue + anotherValue, 0);
    }

    function withTheSameName() public {
        b_var++;
    }

    function withTheSameName(uint aParam) public {
        b_var++;
    }

    function withTheSameName(uint aParam, bool anotherParam) public {
        b_var++;
    }
}

contract C is B {
    uint public c_var;

    constructor() public {
        c_var = 1;
    }

    function cFunction() private {
        c_var++;
    }

    function callsC() public returns (bool) {
        cFunction();

        return c_var <= b_var;
    }
}

contract D is A, C {
    uint public d_var;

    constructor() public {
        d_var = 2;
    }

    function dFunction() public {
        d_var++;
    }

    function toBeOverwritten() public {
        d_var++;
    }
}