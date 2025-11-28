// Line 1: Header comment
// Line 2: More comments
#include <iostream>

// Line 5: Function 1
//@@start func-one
void functionOne() {
    std::cout << "one" << std::endl;
}
//@@end func-one

// Line 12: Function 2 (was line 10, +2 from marker pair above)
void functionTwo() {
    std::cout << "two" << std::endl;
}

// Line 17: Function 3 (was line 15, +2)
//@@start func-three
void functionThree() {
    std::cout << "three" << std::endl;
}
//@@end func-three

// Line 24: Function 4 (was line 20, +4 from two marker pairs)
void functionFour() {
    std::cout << "four" << std::endl;
}

// Line 29: Main (was line 25, +4)
//@@start main-func
int main() {
    functionOne();
    functionTwo();
    functionThree();
    functionFour();
    return 0;
}
//@@end main-func
// Line 39: End of file (was line 33, +6 from three marker pairs)
