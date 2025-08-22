#include <stdio.h>

//@@start add_function
int add(int a, int b) {
    // Simple addition function
    return a + b;
}
//@@end add_function

//@@start multiply_function  
int multiply(int a, int b) {
    // Simple multiplication
    return a * b;
}
//@@end multiply_function

int calculate(int x, int y, int operation) {
    switch(operation) {
        case 0:
            return add(x, y);
        case 1:
            return multiply(x, y);
        default:
            return 0;
    }
}

//@@start main_example
int main() {
    printf("2 + 3 = %d\n", add(2, 3));
    printf("4 * 5 = %d\n", multiply(4, 5));
    printf("Calculate: %d\n", calculate(10, 20, 0));
    return 0;
}
//@@end main_example