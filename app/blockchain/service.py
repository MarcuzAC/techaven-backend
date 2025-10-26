import hashlib
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
import uuid
from .models import Block, Blockchain, BlockchainTransaction, TransactionType

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class BlockchainService:
    def __init__(self):
        self.blockchain = self.create_genesis_block()
    
    def create_genesis_block(self) -> Blockchain:
        """Create the first block in the blockchain"""
        genesis_transaction = BlockchainTransaction(
            transaction_id=str(uuid.uuid4()),
            transaction_type=TransactionType.USER_REGISTER,
            user_id="system",
            timestamp=datetime.now(),
            data={"message": "Genesis block created", "system": "techaven"},
            metadata={"version": "1.0.0"}
        )
        
        genesis_block = Block(
            index=0,
            timestamp=datetime.now(),
            transactions=[genesis_transaction],
            proof=1,
            previous_hash="0" * 64
        )
        genesis_block.hash = self.calculate_hash(genesis_block)
        
        return Blockchain(chain=[genesis_block])
    
    def calculate_hash(self, block: Block) -> str:
        """Calculate SHA-256 hash of a block"""
        block_data = {
            "index": block.index,
            "timestamp": block.timestamp.isoformat(),  # Convert to string
            "transactions": [
                {
                    "transaction_id": tx.transaction_id,
                    "transaction_type": tx.transaction_type,
                    "user_id": tx.user_id,
                    "timestamp": tx.timestamp.isoformat(),  # Convert to string
                    "data": tx.data,
                    "metadata": tx.metadata,
                    "shop_id": tx.shop_id,
                    "product_id": tx.product_id,
                    "order_id": tx.order_id,
                    "promotion_id": tx.promotion_id
                }
                for tx in block.transactions
            ],
            "proof": block.proof,
            "previous_hash": block.previous_hash
        }
        block_string = json.dumps(block_data, sort_keys=True, cls=DateTimeEncoder)
        return hashlib.sha256(block_string.encode()).hexdigest()
    
    def proof_of_work(self, last_proof: int) -> int:
        """Simple proof of work algorithm"""
        proof = 0
        while not self.valid_proof(last_proof, proof):
            proof += 1
        return proof
    
    def valid_proof(self, last_proof: int, proof: int) -> bool:
        """Validate the proof"""
        guess = f"{last_proof}{proof}".encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:self.blockchain.difficulty] == "0" * self.blockchain.difficulty
    
    def create_transaction(self, 
                         transaction_type: TransactionType,
                         user_id: str,
                         data: Dict[str, Any],
                         shop_id: Optional[str] = None,
                         product_id: Optional[str] = None,
                         order_id: Optional[str] = None,
                         promotion_id: Optional[str] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> BlockchainTransaction:
        """Create a new transaction"""
        transaction = BlockchainTransaction(
            transaction_id=str(uuid.uuid4()),
            transaction_type=transaction_type,
            user_id=user_id,
            timestamp=datetime.now(),
            data=data,
            metadata=metadata or {},
            shop_id=shop_id,
            product_id=product_id,
            order_id=order_id,
            promotion_id=promotion_id
        )
        return transaction
    
    def add_transaction(self, transaction: BlockchainTransaction) -> int:
        """Add a transaction to pending transactions"""
        self.blockchain.pending_transactions.append(transaction)
        return self.get_last_block().index + 1
    
    def mine_block(self) -> Block:
        """Mine a new block with pending transactions"""
        if not self.blockchain.pending_transactions:
            raise ValueError("No pending transactions to mine")
        
        last_block = self.get_last_block()
        
        # Mine the proof
        proof = self.proof_of_work(last_block.proof)
        
        # Create new block
        new_block = Block(
            index=len(self.blockchain.chain),
            timestamp=datetime.now(),
            transactions=self.blockchain.pending_transactions.copy(),
            proof=proof,
            previous_hash=last_block.hash
        )
        new_block.hash = self.calculate_hash(new_block)
        
        # Add block to chain and clear pending transactions
        self.blockchain.chain.append(new_block)
        self.blockchain.pending_transactions = []
        
        return new_block
    
    def get_last_block(self) -> Block:
        return self.blockchain.chain[-1]
    
    def is_chain_valid(self) -> bool:
        """Validate the entire blockchain"""
        if len(self.blockchain.chain) == 0:
            return False
            
        for i in range(1, len(self.blockchain.chain)):
            current_block = self.blockchain.chain[i]
            previous_block = self.blockchain.chain[i-1]
            
            # Check hash integrity
            if current_block.hash != self.calculate_hash(current_block):
                return False
            
            # Check chain linkage
            if current_block.previous_hash != previous_block.hash:
                return False
            
            # Check proof of work
            if not self.valid_proof(previous_block.proof, current_block.proof):
                return False
        
        return True
    
    def get_transactions_by_user(self, user_id: str) -> List[BlockchainTransaction]:
        """Get all transactions for a specific user"""
        transactions = []
        for block in self.blockchain.chain:
            for tx in block.transactions:
                if tx.user_id == user_id:
                    transactions.append(tx)
        return transactions
    
    def get_transactions_by_shop(self, shop_id: str) -> List[BlockchainTransaction]:
        """Get all transactions for a specific shop"""
        transactions = []
        for block in self.blockchain.chain:
            for tx in block.transactions:
                if tx.shop_id == shop_id:
                    transactions.append(tx)
        return transactions
    
    def get_transactions_by_product(self, product_id: str) -> List[BlockchainTransaction]:
        """Get all transactions for a specific product"""
        transactions = []
        for block in self.blockchain.chain:
            for tx in block.transactions:
                if tx.product_id == product_id:
                    transactions.append(tx)
        return transactions
    
    def get_transaction_history(self, entity_type: str, entity_id: str) -> List[BlockchainTransaction]:
        """Get transaction history for any entity"""
        transactions = []
        for block in self.blockchain.chain:
            for tx in block.transactions:
                if entity_type == "user" and tx.user_id == entity_id:
                    transactions.append(tx)
                elif entity_type == "shop" and tx.shop_id == entity_id:
                    transactions.append(tx)
                elif entity_type == "product" and tx.product_id == entity_id:
                    transactions.append(tx)
                elif entity_type == "order" and tx.order_id == entity_id:
                    transactions.append(tx)
        return sorted(transactions, key=lambda x: x.timestamp, reverse=True)
    
    def get_blockchain_stats(self) -> Dict[str, Any]:
        """Get blockchain statistics"""
        total_transactions = sum(len(block.transactions) for block in self.blockchain.chain)
        last_block_timestamp = self.get_last_block().timestamp if self.blockchain.chain else None
        
        return {
            "total_blocks": len(self.blockchain.chain),
            "total_transactions": total_transactions,
            "pending_transactions": len(self.blockchain.pending_transactions),
            "chain_valid": self.is_chain_valid(),
            "last_block_timestamp": last_block_timestamp,
            "difficulty": self.blockchain.difficulty
        }

# Global blockchain instance
blockchain_service = BlockchainService()