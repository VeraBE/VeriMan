contract InOrder {
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
        
        if(b_called) {
           num_calls = 0;
           return;
        }

        b_called = true;
        num_calls++;
    }

    function c() public returns(int) {
        require(a_called);
        require(b_called);

        c_called = true;
        num_calls++;

        return 3;
    }
}