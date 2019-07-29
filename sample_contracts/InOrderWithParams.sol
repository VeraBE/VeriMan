contract InOrderWithParams {
    bool public a_called = false;
    bool public b_called = false;
    bool public c_called = false;

    function a(uint pa) public {
        if(pa > 100) {
            a_called = true;
        }
    }

    function b(uint pb) public {
        require(a_called);

        if(pb < 20) {
            b_called = true;
        }
    }


    function c(uint pc) public {
        require(a_called);
        require(b_called);

        c_called = true;

        assert(pc != 40 && pc != 43);
    }
}