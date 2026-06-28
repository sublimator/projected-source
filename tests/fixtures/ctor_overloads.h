// Test fixture: a class whose declared-but-not-defined overload competes with
// a defaulted (function_definition) overload of the same name.
//
// Mirrors the rippled Consensus ctor case: a move-ctor `= default` parses as a
// function_definition, while the "real" ctor is only a declaration inside the
// class body (its body lives out-of-line). Selecting the real ctor by
// signature must not be blocked by the defaulted definition.

namespace demo {

class Consensus {
public:
    // Defaulted -> parses as a function_definition (has a body).
    Consensus(Consensus&&) noexcept = default;

    // Declaration only -> the body is out-of-line below.
    Consensus(clock_type const& clock, Adaptor& adaptor, beast::Journal j);
};

}  // namespace demo
