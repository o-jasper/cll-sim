from sim import Block, Contract, Tx, Simulation, stop, mktx, array
from random import randrange
import inspect, logging, imp
from hashlib import md5
import logging

def sha3(x):
    md5("%s" % x)

# From user.
C_SEND    = 1 # Send immediately.
C_CAGE    = 2 # Store about a transaction and cage it.
# From anyone.
C_RELEASE = 3 # Use a secret to release a caged transaction.

I_BLOCK  = 1000
I_LOCKED = 1001

MIN_FEE = 100

#class SubCurrency(Contract):
#    """See examples/subcurrency.py""" # TODO import somehow instead..
#
#    def run(self, tx, contract, block):
#        Contract.load(self, "examples/subcurrency.cll", tx, contract, block)

class TransactionExchange(Contract):
    """Two parties Alice and Bob want to do transactions, but for each
    only the other guy can actually do it.

    The base idea:
    
    * Alice and Bob tell each other the transaction they want to do.
    
    * Alice creates a secret S, and creates a contract that will do Bobs
      transaction _if_ you know the secret. This is done by checking if
      H(Input) == H(S), and H(S) is the value in the contract.
      (the secret is unknown to Bob at this point)
    
    * Bob now knows that if S is revealed he can activate that contract.
      So he can safely create the contract that sends if H(S)

    * Alice uses the secret S to unlock the one benefitting her. Bob looks
      at the transaction that does it, and does the same thing for his
      transaction.

    * Additionally there is a safety; if it doesnt work out within some
      number of blocks, the whole thing is cancelled.

    This contract has more features yet! Basically instead doing just a
    the above, it can do arbitrary stuff, disables sending to a particular
    address. The reason is because those other contracts probably identity
    the contract itself by the address. So to use the above functionality,
    the adress of the 
    
    ## Applications:
    * For instance the subcurrency example doesnt support Bob buying
      subcurrency coins from Alice.(alice can just give them) Now they can
      ensure that both get what they want.
    * If there are forks of ethereum with separate blockchain, this works as
       wel across blockchains as inside one of them.
    
    ## Improvements
    
    Now in the above, both H(S) and S tie the two events together. We dont
    want that, i expect there is a scheme where Alice and Bob agree on a
    value R and some H implies a HB(H,R) and S implies a SB(S,H,R). In such
    that a third party not knowing R is none the wiser.

    There are probably other approaches..

    If anyone figures out how to have a seamless
    """
    
    def init(owner="pete"):
        return owner

    def run(self, tx, contract, block):
        if tx.value < MIN_FEE * block.basefee:
            stop("Insufficient fee")
        if tx.datan == 0:
            stop("Donation")
        
        if tx.sender == self.owner:
            if tx.data[0] ==  C_SEND:
                if tx.datan < 3:
                    stop("Too few arguments")
                if contract.storage[I_LOCKED] > block.account_balance(contract.address) - tx.data[2]:
                    stop("Not enough left for obligations")
                if contract.storage[I_BLOCK + tx.data[1]] and contract.storage[I_BLOCK + tx.data[1]] < block.number:
                    stop("Blocked")
                arr = array(tx.datan - 3)
                i = 3
                while i < tx.datan:
                    arr[i-3] = tx.data[i]
                    i = i + 1
                mktx(tx.data[1], tx.data[2], tx.datan - 3, arr)
                stop("Sent direct")

            if tx.data[0] == C_CAGE:
                if tx.datan < 5:
                    stop("Too few arguments")
                cage_send_to = tx.data[1]
                if contract.storage[I_BLOCK + cage_send_to]:
                    stop("Blocked for other purpose")
                # Store [length, send_to, expiration_date, H(S), value, ..data..]
                contract.storage[I_LOCKED] += tx.data[4]
                contract.storage[I_BLOCK + cage_send_to] = tx.datan + 4
                i = 1
                while i < tx.datan:
                    contract.storage[I_BLOCK + cage_send_to + i] = tx.data[i]
                    i = i + 1
                stop("Caged a transaction")

        if tx.datan == 2 and tx.data[0] == C_RELEASE:

            release_addr = tx.data[1]
            on_storage = I_BLOCK + release_addr
            L = contract.storage[on_storage]
            if L == 0:
                stop("Nothing to release")
            if contract.storage[on_storage + 2] <= block.number:
                n = L - 1
                while n >= 0: #Free it.
                    contract.storage[on_storage + n] = 0
                    n = n - 1
                stop("Expired")
            if contract.storage[on_storage + 3] != sha3(tx.data[1]):
                stop("Wrong secret")
            if contract.storage[on_storage + 1] != release_addr:
                stop("Oh dear")
            arr = array(L-5)
            value = contract.storage[on_storage + 4]
            i = 0
            while i < L: #Free and create the data to send.
                if i >= 5:
                    arr[i-5] = contract.storage[i]
                contract.storage[i] = 0
                i = i + 1
            mktx(release_addr, value, L - 5, arr)
            contract.storage[I_LOCKED] -= tx.value
            stop("Released")
        stop("Donation")

def rand_arr(arr):
    return arr[randrange(len(arr))]

def random_person():
    return rand_arr(["alice", "bob", "anyone"])

ALICE       = 231
BOB         = 232
SUBCURRENCY = 233

class TransactionExchangeRun(Simulation):
    alice = TransactionExchange()
    alice.owner = "alice"
    bob   = TransactionExchange()
    bob.owner = "bob"
#
#    currency = SubCurrency()
    
    block = Block(number=1)

    def run_tx(self, contract, value=0, sender="", data=[]):
        self.run(Tx(value=value, sender=sender, data=data), contract, self.block,
                 method_name=inspect.stack()[1][3])

    def test_insufficient_fee(self):
        self.run_tx(self.alice, sender=random_person(), value=MIN_FEE - 1)
        self.check(stopped="Insufficient fee")

    def test_donate(self):
        self.run_tx(self.alice, sender=random_person(), value=MIN_FEE + 1)
        logging.info(self.stopped)
        self.check(stopped="Donation")

    def test_donate_wrong_user(self):
        self.run_tx(self.alice, sender="anyone", value=MIN_FEE,
                    data=rand_arr([[C_SEND], [C_CAGE]]))
        self.check(stopped="Donation")
    
    def test_send_direct(self):
        crypto_gods = randrange(100000)
        worship     = randrange(100000)
        self.block.set_account_balance(self.alice.address,10000)
        self.run_tx(self.alice, sender="alice", value=MIN_FEE + randrange(10),
                    data=[C_SEND, crypto_gods, 9000, worship])
        self.check(stopped="Sent direct")
        self.alice.check(txsn=1, txs=[(crypto_gods, 9000, 1, worship)])

    def test_send_direct_over_locked(self):
        crypto_gods = randrange(100000)
        worship     = randrange(100000)
        self.block.set_account_balance(self.alice.address,10000)
        self.alice.storage[I_LOCKED]= 3000
        self.run_tx(self.alice, sender="alice", value=MIN_FEE + randrange(10),
                    data=[C_SEND, crypto_gods, 9000, worship])
        self.check(stopped="Not enough left for obligations")
        self.alice.check(txsn=0)
        self.alice.storage[I_LOCKED]= 0        

    s   = "SUPER SECRET"
    h_s = sha3(s)
    def test_alice_cage(self):
        value = 6000
        self.run_tx(self.alice, sender="alice", value=MIN_FEE,
                    data=[C_CAGE, BOB, 5, self.h_s, value,
                           "payment for bob sending currency coins"])
        self.check(stopped="Caged a transaction")
        self.alice.storage.check_pair_1(I_LOCKED, value)
        self.alice.storage.check_sequence(I_BLOCK + BOB,
                                          [10, BOB, 5, self.h_s, value,
                                           "payment for bob sending currency coins"])

    def test_bob_cage(self):
        value = 1000*self.block.basefee
        subcurrency_coins = 1000
        self.run_tx(self.bob, sender="bob", value=MIN_FEE,
                    data=[C_CAGE, SUBCURRENCY, 5, self.h_s, value, ALICE, subcurrency_coins])
        self.check(stopped="Caged a transaction")
        self.bob.storage.check_pair_1(I_LOCKED, value)
        self.bob.storage.check_sequence(I_BLOCK + SUBCURRENCY,
                                         [11, SUBCURRENCY, 5, self.h_s, value,
                                          ALICE, subcurrency_coins])

    def test_alice_release(self):
        logging.info(self.block.number)
        logging.info(self.alice.storage[I_BLOCK + BOB + 2])
        
        self.run_tx(self.alice, sender=random_person(), value=MIN_FEE,
                    data=[C_RELEASE, BOB])
        self.check(stopped="Released")
        self.alice.storage.check_pair_1(I_LOCKED, 0)
        self.alice.storage.check_sequence(I_BLOCK + BOB, [0]*10)
