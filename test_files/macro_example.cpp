#include <js_api.h>

DEFINE_JS_FUNCTION(example, ctx, data) {
    //@@start setup
    JS_HOOK_SETUP();
    auto context = get_context();
    //@@end setup
    
    //@@start validation
    if (!validate_input(data)) {
        return JS_ERROR;
    }
    //@@end validation
    
    //@@start execution
    perform_operation();
    //@@end execution
    
    return JS_SUCCESS;
}

DEFINE_JS_FUNCTION(another, env, args) {
    //@@start init
    initialize();
    //@@end init
    
    return JS_OK;
}