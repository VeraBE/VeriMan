pragma solidity ^0.5.10;

contract Mappings {
    mapping (int => int) public aMapping;
    int public anInt;

    function setMapping(int aKey, int aValue) public {
        aMapping[aKey] = aValue;
    }

    function setAnInt(int aParam) public {
        anInt = aParam;
    }

    function anotherFunction() public returns (bool) {
        return false;
    }

    function read(int aKey) public returns (int) {
        return aMapping[aKey];
    }
}