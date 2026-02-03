/**
 * Test fixture for class method extraction from headers.
 * These are method declarations, not definitions - common in headers.
 */

#include <string>
#include <vector>
#include <optional>

namespace ripple {

/**
 * Service class for shuffle operations.
 */
class ShuffleService
{
public:
    struct Proposal
    {
        int signingKey;
        int masterKey;
    };

    explicit ShuffleService(int j) : j_(j)
    {
    }

    // Method declarations (not definitions) - typical header style
    bool
    addProposal(
        uint256 const& prevLedger,
        uint256 const& txSetHash,
        PublicKey const& signingPubKey,
        PublicKey const& masterPubKey);

    std::vector<Proposal>
    getProposals(Digest const& digest) const;

    std::size_t
    proposalCount(Digest const& digest) const;

    // Static methods
    static Serializer
    buildSigningData(uint256 const& prevLedger, uint256 const& txSetHash);

    static Digest
    computeDigest(uint256 const& prevLedger, uint256 const& txSetHash);

    // Overloaded methods
    std::optional<uint256>
    computeCombinedEntropy(Digest const& digest) const;

    static uint256
    computeCombinedEntropy(
        uint256 const& txSetHash,
        std::vector<std::pair<NodeID, Slice>> const& contributions);

    void reset(uint256 const& prevLedger, uint256 const& txSetHash);

private:
    int j_;
};

// Template functions with overloads
template <class V>
bool
inUNLReport(V const& view, AccountID const& id, beast::Journal const& j)
{
    return true;
}

template <class V>
bool
inUNLReport(V const& view, Application& app, PublicKey const& pk, beast::Journal const& j)
{
    return true;
}

// Simple template function
template <typename T>
T processData(T const& input, int flags)
{
    return input;
}

}  // namespace ripple
