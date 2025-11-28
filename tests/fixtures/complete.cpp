// STATIC TEST FILE - DO NOT MODIFY
// Complete C++ test fixture with various structures for testing extraction

// Simple struct
struct SimpleStruct {
    int x;
    int y;
};

// Simple class
class SimpleClass {
public:
    void method() {
        // method implementation
    }
private:
    int data;
};

// Namespace with struct and class
namespace MyNamespace {
    struct NamespacedStruct {
        float value;
    };
    
    class NamespacedClass {
    public:
        int getValue() const { return 42; }
    };
    
    // Nested namespace
    namespace Inner {
        struct DeepStruct {
            bool flag;
        };
    }
}

// Nested classes and structs
class OuterClass {
public:
    struct InnerStruct {
        bool flag;
    };
    
    class InnerClass {
    public:
        void doSomething() {}
    };
    
    // Deeply nested
    class MiddleClass {
    public:
        struct DeepStruct {
            int deep_value;
        };
    };
};

// Functions
void simpleFunction() {
    // function body
}

int functionWithMarkers(int a, int b) {
    //@@start setup
    int temp = a + b;
    //@@end setup
    
    //@@start calculation
    int result = temp * 2;
    //@@end calculation
    
    //@@start saving-ledger
    // Simulated save operation
    if (result > 0) {
        // save to ledger
    }
    //@@end saving-ledger
    
    return result;
}

namespace FunctionNamespace {
    int namespacedFunction(int x) {
        return x * 2;
    }
    
    void namespacedFunctionWithMarker(int value) {
        //@@start processing
        int processed = value * value;
        std::cout << processed << std::endl;
        //@@end processing
    }
}

class ClassWithMethods {
public:
    void simpleMethod() {}
    static int staticMethod(int x) { return x; }
    
    int methodWithMarker(int input) {
        //@@start validation
        if (input < 0) {
            return -1;
        }
        //@@end validation
        
        //@@start computation
        int output = input * input + input;
        //@@end computation
        
        return output;
    }
    
    // Nested class with method
    class Nested {
    public:
        void nestedMethod() {}
    };
};

// Function-defining macros
#define DEFINE_JS_FUNCTION(return_type, name, ...) \
    JSValue JSFunction##name(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)

DEFINE_JS_FUNCTION(JSValue, testFunc, int32_t, value1, int32_t, value2) {
    //@@start example1
    int sum = value1 + value2;
    //@@end example1
    return JS_NewInt32(ctx, sum);
}

DEFINE_JS_FUNCTION(JSValue, anotherFunc, int32_t, x) {
    //@@start calculation
    int result = x * x;
    //@@end calculation
    return JS_NewInt32(ctx, result);
}

// Macro definitions
#define MAX_SIZE 1024
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define COMPLEX_MACRO(x, y) \
    do { \
        int temp = (x); \
        (x) = (y); \
        (y) = temp; \
    } while(0)

// Template class
template<typename T>
class TemplateClass {
public:
    T getValue() { return value; }
private:
    T value;
};

// Template specialization
template<>
class TemplateClass<int> {
public:
    int getValue() { return 42; }
};