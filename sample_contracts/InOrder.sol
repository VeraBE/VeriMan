contract InOrder {
    bool public a_called = false;
    bool public b_called = false;
    bool public c_called = false;

    function a() public {
        a_called = true;
    }

    function b() public {
        require(a_called);

        b_called = true;
    }


    function c() public {
        require(a_called);
        require(b_called);

        c_called = true;

        assert(false);
    }
}