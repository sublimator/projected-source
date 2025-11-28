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
    void setValue(T v) { value = v; }
private:
    T value;
};

// Template specialization
template<>
class TemplateClass<int> {
public:
    int getValue() { return 42; }
};

// ============================================================
// INLINE FUNCTIONS
// ============================================================

// Simple inline function
inline int inlineAdd(int a, int b) {
    return a + b;
}

// Static inline function
static inline void staticInlineFunc() {
    // static inline body
}

// Inline with complex return type
inline std::optional<std::vector<uint8_t>>
inlineComplexReturn(int max_len) {
    return std::nullopt;
}

// ============================================================
// TEMPLATE FUNCTIONS
// ============================================================

// Simple template function
template<typename T>
T templateAdd(T a, T b) {
    return a + b;
}

// Template function with multiple type params
template<typename T, typename U>
auto templateMulti(T a, U b) -> decltype(a + b) {
    return a + b;
}

// Template function specialization
template<>
int templateAdd<int>(int a, int b) {
    return a + b + 1;  // specialized version
}

// ============================================================
// OUT-OF-LINE TEMPLATE METHODS
// ============================================================

template<typename T>
class Container {
public:
    void add(T item);
    T get(int index) const;
private:
    std::vector<T> items;
};

template<typename T>
void Container<T>::add(T item) {
    items.push_back(item);
}

template<typename T>
T Container<T>::get(int index) const {
    return items[index];
}

// ============================================================
// OPERATOR OVERLOADS
// ============================================================

class Vector2D {
public:
    float x, y;

    Vector2D operator+(const Vector2D& other) const {
        return Vector2D{x + other.x, y + other.y};
    }

    Vector2D& operator+=(const Vector2D& other) {
        x += other.x;
        y += other.y;
        return *this;
    }

    bool operator==(const Vector2D& other) const {
        return x == other.x && y == other.y;
    }

    float operator[](int index) const {
        return index == 0 ? x : y;
    }

    // Conversion operator
    explicit operator bool() const {
        return x != 0 || y != 0;
    }
};

// Out-of-line operator
Vector2D operator*(const Vector2D& v, float scalar) {
    return Vector2D{v.x * scalar, v.y * scalar};
}

// ============================================================
// CONSTEXPR AND CONSTEVAL
// ============================================================

constexpr int constexprFactorial(int n) {
    return n <= 1 ? 1 : n * constexprFactorial(n - 1);
}

// ============================================================
// VIRTUAL FUNCTIONS
// ============================================================

class Base {
public:
    virtual void virtualFunc() {
        // base implementation
    }
    virtual int pureVirtual() = 0;
    virtual ~Base() = default;
};

class Derived : public Base {
public:
    void virtualFunc() override {
        // derived implementation
    }
    int pureVirtual() override {
        return 42;
    }
};

// ============================================================
// EXTERN C
// ============================================================

extern "C" {
    void externCFunc() {
        // C linkage function
    }

    int externCWithReturn(int x) {
        return x * 2;
    }
}

// ============================================================
// FRIEND FUNCTIONS
// ============================================================

class SecretHolder {
    friend void revealSecret(SecretHolder& holder);
    int secret = 42;
};

void revealSecret(SecretHolder& holder) {
    holder.secret = 0;
}

// ============================================================
// NOEXCEPT AND ATTRIBUTES
// ============================================================

void noexceptFunc() noexcept {
    // guaranteed not to throw
}

[[nodiscard]] int nodiscardFunc() {
    return 42;
}

[[deprecated("use newFunc instead")]]
void deprecatedFunc() {
    // old implementation
}