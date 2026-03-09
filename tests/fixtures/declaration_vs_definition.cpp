// Test fixture: declaration vs out-of-line definition

class NetworkOPsImp {
public:
    void setAmendmentBlocked() override;
    int getValue() const;
    void process(int x);
};

// Out-of-line definitions
void
NetworkOPsImp::setAmendmentBlocked()
{
    // This is the actual implementation
    blocked_ = true;
    notify();
}

int
NetworkOPsImp::getValue() const
{
    return value_;
}

void
NetworkOPsImp::process(int x)
{
    // process implementation
    value_ = x * 2;
}
