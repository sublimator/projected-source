/**
 * Test fixture for overloaded function disambiguation.
 */

#include <memory>
#include <string>

namespace protocol {
    struct TMProposeSet { int data; };
    struct TMTransaction { int data; };
    struct TMGetLedger { int data; };
    struct TMValidation { int data; };
}

class PeerImp {
public:
    // Multiple overloads of onMessage with different protocol types
    void onMessage(std::shared_ptr<protocol::TMProposeSet> const& m) {
        // Handle proposal set
        processProposal(m->data);
    }

    void onMessage(std::shared_ptr<protocol::TMTransaction> const& m) {
        // Handle transaction
        processTransaction(m->data);
    }

    void onMessage(std::shared_ptr<protocol::TMGetLedger> const& m) {
        // Handle ledger request
        processLedgerRequest(m->data);
    }

    void onMessage(std::shared_ptr<protocol::TMValidation> const& m) {
        // Handle validation
        processValidation(m->data);
    }

    // Overloads with primitive types
    void process(int value) {
        // Integer processing
        handleInt(value);
    }

    void process(const std::string& value) {
        // String processing
        handleString(value);
    }

    void process(int a, int b) {
        // Two integers
        handleIntPair(a, b);
    }

private:
    void processProposal(int) {}
    void processTransaction(int) {}
    void processLedgerRequest(int) {}
    void processValidation(int) {}
    void handleInt(int) {}
    void handleString(const std::string&) {}
    void handleIntPair(int, int) {}
};

// Free function overloads
void handleEvent(int code) {
    // Handle by code
}

void handleEvent(const std::string& name) {
    // Handle by name
}

void handleEvent(int code, const std::string& message) {
    // Handle with code and message
}
