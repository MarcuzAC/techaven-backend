import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from uuid import uuid4
import logging
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
import base64
import asyncio
from contextlib import asynccontextmanager

from sqlalchemy.orm import Session
from model.models import BlockchainTransaction as BlockchainTransactionModel, Block as BlockModel
# Correct import path - use the same as your notification routes
from app.model.models import (
    BlockchainTransaction, Block, Blockchain,
    BlockchainTransactionResponse, BlockResponse, ChainValidationResponse,
    BlockchainStatsResponse, NodeRegistration, MiningRequest, MiningResponse,
    TransactionType  # Import TransactionType enum from your models
)
from config import settings
from utils.security import generate_secure_token, generate_hmac_signature, verify_hmac_signature

logger = logging.getLogger(__name__)

class BlockchainService:
    """Blockchain service for transaction immutability and verification."""
    
    def __init__(self, db: Session = None):
        self.db = db
        self.difficulty = settings.BLOCKCHAIN_DIFFICULTY
        self.mining_reward = settings.MINING_REWARD
        self.nodes = set()
        
        # Load or initialize blockchain
        self.chain = self._load_chain_from_db()
        
        # Create genesis block if chain is empty
        if not self.chain:
            self._create_genesis_block()
        
        # Current transactions waiting to be mined
        self.pending_transactions = []
        
        # RSA key pair for digital signatures
        self.private_key = None
        self.public_key = None
        self._load_or_generate_keys()
        
        logger.info(f"Blockchain initialized with {len(self.chain)} blocks")
    
    def _load_chain_from_db(self) -> List[Block]:
        """Load blockchain from database."""
        if not self.db:
            return []
        
        try:
            blocks = self.db.query(BlockModel).order_by(BlockModel.index).all()
            
            chain = []
            for block in blocks:
                # Load transactions
                transactions = []
                for tx in block.transactions:
                    transactions.append(BlockchainTransaction(
                        transaction_id=tx.transaction_id,
                        transaction_type=TransactionType(tx.transaction_type),  # Use TransactionType enum
                        user_id=tx.user_id,
                        timestamp=tx.timestamp,
                        data=tx.data,
                        metadata=tx.metadata,
                        signature=tx.signature,
                        previous_hash=tx.previous_hash,
                        shop_id=tx.shop_id,
                        product_id=tx.product_id,
                        order_id=tx.order_id,
                        promotion_id=tx.promotion_id,
                        category_id=tx.category_id,
                        review_id=tx.review_id,
                        payment_id=tx.payment_id
                    ))
                
                chain.append(Block(
                    index=block.index,
                    timestamp=block.timestamp,
                    transactions=transactions,
                    proof=block.proof,
                    previous_hash=block.previous_hash,
                    nonce=block.nonce,
                    hash=block.hash,
                    mined_by=block.mined_by,
                    difficulty=block.difficulty
                ))
            
            return chain
            
        except Exception as e:
            logger.error(f"Error loading blockchain from database: {str(e)}")
            return []
    
    def _save_block_to_db(self, block: Block) -> bool:
        """Save block to database."""
        if not self.db:
            return False
        
        try:
            # Save block
            db_block = BlockModel(
                index=block.index,
                timestamp=block.timestamp,
                proof=block.proof,
                previous_hash=block.previous_hash,
                nonce=block.nonce,
                hash=block.hash,
                mined_by=block.mined_by,
                difficulty=block.difficulty
            )
            
            self.db.add(db_block)
            self.db.flush()  # Get block ID
            
            # Save transactions
            for tx in block.transactions:
                db_tx = BlockchainTransactionModel(
                    transaction_id=tx.transaction_id,
                    transaction_type=tx.transaction_type.value,  # Store string value
                    user_id=tx.user_id,
                    timestamp=tx.timestamp,
                    data=tx.data,
                    metadata=tx.metadata,
                    signature=tx.signature,
                    previous_hash=tx.previous_hash,
                    shop_id=tx.shop_id,
                    product_id=tx.product_id,
                    order_id=tx.order_id,
                    promotion_id=tx.promotion_id,
                    category_id=tx.category_id,
                    review_id=tx.review_id,
                    payment_id=tx.payment_id,
                    block_id=db_block.id
                )
                self.db.add(db_tx)
            
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving block to database: {str(e)}")
            return False
    
    def _create_genesis_block(self) -> None:
        """Create the genesis block."""
        genesis_block = Block(
            index=0,
            timestamp=datetime.utcnow(),
            transactions=[],
            proof=100,
            previous_hash="0" * 64,
            nonce=0,
            mined_by="system",
            difficulty=self.difficulty
        )
        
        # Calculate hash
        genesis_block.hash = self._calculate_block_hash(genesis_block)
        
        # Save to chain
        self.chain = [genesis_block]
        
        # Save to database if available
        if self.db:
            self._save_block_to_db(genesis_block)
        
        logger.info("Genesis block created")
    
    def _load_or_generate_keys(self) -> None:
        """Load or generate RSA key pair for digital signatures."""
        try:
            # In production, load keys from secure storage
            # For now, generate new keys
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            
            self.public_key = self.private_key.public_key()
            
            logger.info("RSA key pair generated for digital signatures")
            
        except Exception as e:
            logger.error(f"Error generating RSA keys: {str(e)}")
            raise
    
    def _calculate_hash(self, data: str) -> str:
        """Calculate SHA-256 hash of data."""
        return hashlib.sha256(data.encode()).hexdigest()
    
    def _calculate_block_hash(self, block: Block) -> str:
        """Calculate hash of a block."""
        block_string = json.dumps({
            "index": block.index,
            "timestamp": block.timestamp.isoformat(),
            "transactions": [
                {
                    "transaction_id": tx.transaction_id,
                    "transaction_type": tx.transaction_type.value,  # Use .value for enum
                    "user_id": tx.user_id,
                    "timestamp": tx.timestamp.isoformat(),
                    "data": tx.data
                }
                for tx in block.transactions
            ],
            "proof": block.proof,
            "previous_hash": block.previous_hash,
            "nonce": block.nonce,
            "mined_by": block.mined_by,
            "difficulty": block.difficulty
        }, sort_keys=True)
        
        return self._calculate_hash(block_string)
    
    def _sign_transaction(self, transaction: Dict[str, Any]) -> str:
        """Sign a transaction with private key."""
        try:
            # Create message to sign
            message = json.dumps(transaction, sort_keys=True).encode()
            
            # Sign with private key
            signature = self.private_key.sign(
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Return base64 encoded signature
            return base64.b64encode(signature).decode()
            
        except Exception as e:
            logger.error(f"Error signing transaction: {str(e)}")
            return ""
    
    def _verify_signature(self, transaction: Dict[str, Any], signature: str) -> bool:
        """Verify transaction signature with public key."""
        try:
            # Decode signature
            signature_bytes = base64.b64decode(signature)
            
            # Create message
            message = json.dumps(transaction, sort_keys=True).encode()
            
            # Verify signature
            self.public_key.verify(
                signature_bytes,
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            return True
            
        except InvalidSignature:
            return False
        except Exception as e:
            logger.error(f"Error verifying signature: {str(e)}")
            return False
    
    def get_last_block(self) -> Block:
        """Get the last block in the chain."""
        return self.chain[-1]
    
    def create_transaction(
        self,
        transaction_type: TransactionType,  # Use TransactionType enum
        user_id: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        shop_id: Optional[str] = None,
        product_id: Optional[str] = None,
        order_id: Optional[str] = None,
        promotion_id: Optional[str] = None,
        category_id: Optional[str] = None,
        review_id: Optional[str] = None,
        payment_id: Optional[str] = None
    ) -> BlockchainTransaction:
        """Create a new blockchain transaction."""
        # Create transaction
        transaction = BlockchainTransaction(
            transaction_id=str(uuid4()),
            transaction_type=transaction_type,  # Use TransactionType enum
            user_id=user_id,
            timestamp=datetime.utcnow(),
            data=data,
            metadata=metadata or {},
            shop_id=shop_id,
            product_id=product_id,
            order_id=order_id,
            promotion_id=promotion_id,
            category_id=category_id,
            review_id=review_id,
            payment_id=payment_id,
            previous_hash=self.get_last_block().hash
        )
        
        # Sign the transaction
        transaction_data = {
            "transaction_id": transaction.transaction_id,
            "transaction_type": transaction.transaction_type.value,  # Use .value for enum
            "user_id": transaction.user_id,
            "timestamp": transaction.timestamp.isoformat(),
            "data": transaction.data,
            "metadata": transaction.metadata,
            "previous_hash": transaction.previous_hash
        }
        
        transaction.signature = self._sign_transaction(transaction_data)
        
        # Add to pending transactions
        self.pending_transactions.append(transaction)
        
        logger.info(f"Transaction created: {transaction.transaction_id} ({transaction.transaction_type.value})")
        
        return transaction
    
    async def create_blockchain_transaction(
        self,
        transaction_type: TransactionType,  # Use TransactionType enum
        user_id: str,
        data: Dict[str, Any],
        **kwargs
    ) -> BlockchainTransaction:
        """Create blockchain transaction (async wrapper)."""
        return self.create_transaction(transaction_type, user_id, data, **kwargs)
    
    def mine_block(self, miner_address: str) -> Optional[Block]:
        """Mine a new block with pending transactions."""
        if not self.pending_transactions:
            return None
        
        last_block = self.get_last_block()
        
        # Create mining reward transaction
        # Note: "mining_reward" is not in TransactionType enum, so we'll handle it specially
        reward_transaction = BlockchainTransaction(
            transaction_id=str(uuid4()),
            transaction_type="mining_reward",  # Special type not in enum
            user_id=miner_address,
            timestamp=datetime.utcnow(),
            data={"amount": self.mining_reward, "reason": "Block mining reward"},
            metadata={},
            previous_hash=last_block.hash
        )
        
        # Add reward to transactions
        transactions_to_mine = self.pending_transactions + [reward_transaction]
        
        # Create new block
        new_block = Block(
            index=last_block.index + 1,
            timestamp=datetime.utcnow(),
            transactions=transactions_to_mine,
            proof=0,  # Will be set during mining
            previous_hash=last_block.hash,
            nonce=0,
            mined_by=miner_address,
            difficulty=self.difficulty
        )
        
        # Mine the block (proof of work)
        logger.info(f"Mining block #{new_block.index} with {len(transactions_to_mine)} transactions...")
        
        start_time = time.time()
        new_block = self._proof_of_work(new_block)
        mining_time = time.time() - start_time
        
        # Calculate block hash
        new_block.hash = self._calculate_block_hash(new_block)
        
        # Add block to chain
        self.chain.append(new_block)
        
        # Clear pending transactions
        self.pending_transactions = []
        
        # Save to database
        if self.db:
            self._save_block_to_db(new_block)
        
        logger.info(
            f"Block #{new_block.index} mined by {miner_address} "
            f"in {mining_time:.2f}s (nonce: {new_block.nonce})"
        )
        
        return new_block
    
    def _proof_of_work(self, block: Block) -> Block:
        """Perform proof of work to find valid nonce."""
        block.nonce = 0
        target_prefix = "0" * self.difficulty
        
        while True:
            block_hash = self._calculate_block_hash(block)
            if block_hash.startswith(target_prefix):
                block.proof = block.nonce
                return block
            
            block.nonce += 1
            
            # Prevent infinite loop
            if block.nonce % 10000 == 0:
                logger.debug(f"Testing nonce {block.nonce}...")
    
    def is_chain_valid(self) -> ChainValidationResponse:
        """Validate the entire blockchain."""
        issues = []
        
        # Check each block
        for i in range(1, len(self.chain)):
            current_block = self.chain[i]
            previous_block = self.chain[i - 1]
            
            # Check block hash
            calculated_hash = self._calculate_block_hash(current_block)
            if current_block.hash != calculated_hash:
                issues.append(f"Block #{current_block.index}: Invalid hash")
            
            # Check previous hash
            if current_block.previous_hash != previous_block.hash:
                issues.append(f"Block #{current_block.index}: Invalid previous hash")
            
            # Check proof of work
            target_prefix = "0" * current_block.difficulty
            if not current_block.hash.startswith(target_prefix):
                issues.append(f"Block #{current_block.index}: Invalid proof of work")
            
            # Check transaction signatures
            for tx in current_block.transactions:
                # Mining rewards aren't signed and may not be TransactionType enum
                if not hasattr(tx.transaction_type, 'value') or tx.transaction_type.value != "mining_reward":
                    tx_type_value = tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type)
                    
                    tx_data = {
                        "transaction_id": tx.transaction_id,
                        "transaction_type": tx_type_value,
                        "user_id": tx.user_id,
                        "timestamp": tx.timestamp.isoformat(),
                        "data": tx.data,
                        "metadata": tx.metadata,
                        "previous_hash": tx.previous_hash
                    }
                    
                    if not self._verify_signature(tx_data, tx.signature):
                        issues.append(f"Block #{current_block.index}, Transaction {tx.transaction_id}: Invalid signature")
        
        return ChainValidationResponse(
            is_valid=len(issues) == 0,
            total_blocks=len(self.chain),
            total_transactions=sum(len(block.transactions) for block in self.chain),
            pending_transactions=len(self.pending_transactions),
            issues=issues,
            chain_hash=self._calculate_chain_hash()
        )
    
    def _calculate_chain_hash(self) -> str:
        """Calculate hash of the entire chain."""
        chain_data = json.dumps([
            {
                "index": block.index,
                "hash": block.hash,
                "timestamp": block.timestamp.isoformat()
            }
            for block in self.chain
        ], sort_keys=True)
        
        return self._calculate_hash(chain_data)
    
    def get_transaction_by_id(self, transaction_id: str) -> Optional[BlockchainTransactionResponse]:
        """Get transaction by ID from blockchain."""
        for block in self.chain:
            for tx in block.transactions:
                if tx.transaction_id == transaction_id:
                    tx_type_value = tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type)
                    
                    return BlockchainTransactionResponse(
                        transaction_id=tx.transaction_id,
                        transaction_type=tx_type_value,
                        user_id=tx.user_id,
                        timestamp=tx.timestamp,
                        data=tx.data,
                        block_index=block.index,
                        block_hash=block.hash,
                        confirmed=True,
                        confirmations=len(self.chain) - block.index
                    )
        
        # Check pending transactions
        for tx in self.pending_transactions:
            if tx.transaction_id == transaction_id:
                tx_type_value = tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type)
                
                return BlockchainTransactionResponse(
                    transaction_id=tx.transaction_id,
                    transaction_type=tx_type_value,
                    user_id=tx.user_id,
                    timestamp=tx.timestamp,
                    data=tx.data,
                    confirmed=False,
                    confirmations=0
                )
        
        return None
    
    def get_user_transactions(self, user_id: str, limit: int = 100) -> List[BlockchainTransactionResponse]:
        """Get all transactions for a user."""
        transactions = []
        
        # Get from blockchain (confirmed)
        for block in reversed(self.chain):  # Most recent first
            for tx in block.transactions:
                if tx.user_id == user_id:
                    tx_type_value = tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type)
                    
                    transactions.append(BlockchainTransactionResponse(
                        transaction_id=tx.transaction_id,
                        transaction_type=tx_type_value,
                        user_id=tx.user_id,
                        timestamp=tx.timestamp,
                        data=tx.data,
                        block_index=block.index,
                        block_hash=block.hash,
                        confirmed=True,
                        confirmations=len(self.chain) - block.index
                    ))
                    
                    if len(transactions) >= limit:
                        return transactions
        
        # Get pending transactions
        for tx in self.pending_transactions:
            if tx.user_id == user_id:
                tx_type_value = tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type)
                
                transactions.append(BlockchainTransactionResponse(
                    transaction_id=tx.transaction_id,
                    transaction_type=tx_type_value,
                    user_id=tx.user_id,
                    timestamp=tx.timestamp,
                    data=tx.data,
                    confirmed=False,
                    confirmations=0
                ))
                
                if len(transactions) >= limit:
                    break
        
        return transactions
    
    def get_entity_transactions(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100
    ) -> List[BlockchainTransactionResponse]:
        """Get all transactions for an entity (product, order, etc.)."""
        transactions = []
        entity_field = f"{entity_type}_id"
        
        for block in reversed(self.chain):
            for tx in block.transactions:
                entity_value = getattr(tx, entity_field, None)
                if entity_value == entity_id:
                    tx_type_value = tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type)
                    
                    transactions.append(BlockchainTransactionResponse(
                        transaction_id=tx.transaction_id,
                        transaction_type=tx_type_value,
                        user_id=tx.user_id,
                        timestamp=tx.timestamp,
                        data=tx.data,
                        block_index=block.index,
                        block_hash=block.hash,
                        confirmed=True,
                        confirmations=len(self.chain) - block.index
                    ))
                    
                    if len(transactions) >= limit:
                        return transactions
        
        return transactions
    
    def get_blockchain_stats(self) -> BlockchainStatsResponse:
        """Get blockchain statistics."""
        last_block = self.get_last_block() if self.chain else None
        
        total_transactions = sum(len(block.transactions) for block in self.chain)
        
        # Calculate mining rewards
        total_mining_rewards = 0
        for block in self.chain:
            for tx in block.transactions:
                tx_type_value = tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type)
                if tx_type_value == "mining_reward":
                    total_mining_rewards += tx.data.get("amount", 0)
        
        validation = self.is_chain_valid()
        
        return BlockchainStatsResponse(
            total_blocks=len(self.chain),
            total_transactions=total_transactions,
            pending_transactions=len(self.pending_transactions),
            chain_valid=validation.is_valid,
            last_block_timestamp=last_block.timestamp if last_block else None,
            last_block_hash=last_block.hash if last_block else None,
            difficulty=self.difficulty,
            mining_reward=self.mining_reward,
            node_count=len(self.nodes),
            total_mining_rewards=total_mining_rewards
        )
    
    def register_node(self, node_address: str) -> bool:
        """Register a new node in the network."""
        if node_address not in self.nodes:
            self.nodes.add(node_address)
            logger.info(f"Node registered: {node_address}")
            return True
        return False
    
    def resolve_conflicts(self) -> bool:
        """Consensus algorithm to resolve conflicts."""
        if not self.nodes:
            return False
        
        new_chain = None
        max_length = len(self.chain)
        
        # Get chains from all nodes
        # In production, this would make HTTP requests to nodes
        # For now, we'll simulate by checking if our chain is the longest
        
        # If we found a longer valid chain, replace ours
        if new_chain:
            self.chain = new_chain
            logger.info("Chain replaced via consensus")
            return True
        
        return False
    
    # Database operations
    def save_transaction_to_db(self, transaction: BlockchainTransaction) -> bool:
        """Save transaction to database (without block)."""
        if not self.db:
            return False
        
        try:
            tx_type_value = transaction.transaction_type.value if hasattr(transaction.transaction_type, 'value') else str(transaction.transaction_type)
            
            db_tx = BlockchainTransactionModel(
                transaction_id=transaction.transaction_id,
                transaction_type=tx_type_value,  # Store string value
                user_id=transaction.user_id,
                timestamp=transaction.timestamp,
                data=transaction.data,
                metadata=transaction.metadata,
                signature=transaction.signature,
                previous_hash=transaction.previous_hash,
                shop_id=transaction.shop_id,
                product_id=transaction.product_id,
                order_id=transaction.order_id,
                promotion_id=transaction.promotion_id,
                category_id=transaction.category_id,
                review_id=transaction.review_id,
                payment_id=transaction.payment_id
            )
            
            self.db.add(db_tx)
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving transaction to database: {str(e)}")
            return False
    
    def get_recent_transactions(self, limit: int = 50) -> List[BlockchainTransactionResponse]:
        """Get recent transactions from blockchain."""
        transactions = []
        
        # Get from most recent blocks
        for block in reversed(self.chain):
            for tx in reversed(block.transactions):
                tx_type_value = tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type)
                
                transactions.append(BlockchainTransactionResponse(
                    transaction_id=tx.transaction_id,
                    transaction_type=tx_type_value,
                    user_id=tx.user_id,
                    timestamp=tx.timestamp,
                    data=tx.data,
                    block_index=block.index,
                    block_hash=block.hash,
                    confirmed=True,
                    confirmations=len(self.chain) - block.index
                ))
                
                if len(transactions) >= limit:
                    return transactions
        
        # Add pending transactions
        for tx in self.pending_transactions:
            tx_type_value = tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type)
            
            transactions.append(BlockchainTransactionResponse(
                transaction_id=tx.transaction_id,
                transaction_type=tx_type_value,
                user_id=tx.user_id,
                timestamp=tx.timestamp,
                data=tx.data,
                confirmed=False,
                confirmations=0
            ))
            
            if len(transactions) >= limit:
                break
        
        return transactions
    
    def search_transactions(
        self,
        search_term: str,
        transaction_type: Optional[str] = None,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[BlockchainTransactionResponse]:
        """Search transactions with filters."""
        results = []
        
        for block in reversed(self.chain):
            for tx in block.transactions:
                tx_type_value = tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type)
                
                # Apply filters
                if transaction_type and tx_type_value != transaction_type:
                    continue
                
                if user_id and tx.user_id != user_id:
                    continue
                
                if start_date and tx.timestamp < start_date:
                    continue
                
                if end_date and tx.timestamp > end_date:
                    continue
                
                # Search in data
                matches_search = False
                if search_term:
                    # Search in transaction data
                    data_str = json.dumps(tx.data).lower()
                    if search_term.lower() in data_str:
                        matches_search = True
                    
                    # Search in metadata
                    if tx.metadata:
                        metadata_str = json.dumps(tx.metadata).lower()
                        if search_term.lower() in metadata_str:
                            matches_search = True
                    
                    # Search in transaction ID
                    if search_term.lower() in tx.transaction_id.lower():
                        matches_search = True
                else:
                    matches_search = True
                
                if matches_search:
                    results.append(BlockchainTransactionResponse(
                        transaction_id=tx.transaction_id,
                        transaction_type=tx_type_value,
                        user_id=tx.user_id,
                        timestamp=tx.timestamp,
                        data=tx.data,
                        block_index=block.index,
                        block_hash=block.hash,
                        confirmed=True,
                        confirmations=len(self.chain) - block.index
                    ))
                    
                    if len(results) >= limit:
                        return results
        
        return results
    
    # Export/Import
    def export_chain(self, format: str = "json") -> Dict[str, Any]:
        """Export blockchain data."""
        chain_data = []
        
        for block in self.chain:
            block_data = {
                "index": block.index,
                "timestamp": block.timestamp.isoformat(),
                "hash": block.hash,
                "previous_hash": block.previous_hash,
                "proof": block.proof,
                "nonce": block.nonce,
                "mined_by": block.mined_by,
                "difficulty": block.difficulty,
                "transactions": []
            }
            
            for tx in block.transactions:
                tx_type_value = tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type)
                
                tx_data = {
                    "transaction_id": tx.transaction_id,
                    "transaction_type": tx_type_value,
                    "user_id": tx.user_id,
                    "timestamp": tx.timestamp.isoformat(),
                    "data": tx.data,
                    "metadata": tx.metadata,
                    "signature": tx.signature,
                    "previous_hash": tx.previous_hash,
                    "shop_id": tx.shop_id,
                    "product_id": tx.product_id,
                    "order_id": tx.order_id,
                    "promotion_id": tx.promotion_id,
                    "category_id": tx.category_id,
                    "review_id": tx.review_id,
                    "payment_id": tx.payment_id
                }
                block_data["transactions"].append(tx_data)
            
            chain_data.append(block_data)
        
        return {
            "chain": chain_data,
            "pending_transactions": [
                {
                    "transaction_id": tx.transaction_id,
                    "transaction_type": tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type),
                    "user_id": tx.user_id,
                    "timestamp": tx.timestamp.isoformat(),
                    "data": tx.data,
                    "metadata": tx.metadata,
                    "signature": tx.signature,
                    "previous_hash": tx.previous_hash
                }
                for tx in self.pending_transactions
            ],
            "nodes": list(self.nodes),
            "difficulty": self.difficulty,
            "mining_reward": self.mining_reward,
            "exported_at": datetime.utcnow().isoformat(),
            "chain_hash": self._calculate_chain_hash()
        }
    
    def import_chain(self, chain_data: Dict[str, Any]) -> bool:
        """Import blockchain data."""
        try:
            # Validate chain
            imported_chain = []
            
            for block_data in chain_data.get("chain", []):
                # Convert transactions
                transactions = []
                for tx_data in block_data.get("transactions", []):
                    try:
                        # Try to convert to TransactionType enum
                        tx_type = TransactionType(tx_data["transaction_type"])
                    except ValueError:
                        # If it's not a valid TransactionType (e.g., "mining_reward"), use as string
                        tx_type = tx_data["transaction_type"]
                    
                    tx = BlockchainTransaction(
                        transaction_id=tx_data["transaction_id"],
                        transaction_type=tx_type,
                        user_id=tx_data["user_id"],
                        timestamp=datetime.fromisoformat(tx_data["timestamp"]),
                        data=tx_data["data"],
                        metadata=tx_data.get("metadata", {}),
                        signature=tx_data.get("signature"),
                        previous_hash=tx_data.get("previous_hash"),
                        shop_id=tx_data.get("shop_id"),
                        product_id=tx_data.get("product_id"),
                        order_id=tx_data.get("order_id"),
                        promotion_id=tx_data.get("promotion_id"),
                        category_id=tx_data.get("category_id"),
                        review_id=tx_data.get("review_id"),
                        payment_id=tx_data.get("payment_id")
                    )
                    transactions.append(tx)
                
                block = Block(
                    index=block_data["index"],
                    timestamp=datetime.fromisoformat(block_data["timestamp"]),
                    transactions=transactions,
                    proof=block_data["proof"],
                    previous_hash=block_data["previous_hash"],
                    nonce=block_data.get("nonce", 0),
                    hash=block_data["hash"],
                    mined_by=block_data.get("mined_by"),
                    difficulty=block_data.get("difficulty", self.difficulty)
                )
                imported_chain.append(block)
            
            # Validate imported chain
            temp_service = BlockchainService()
            temp_service.chain = imported_chain
            validation = temp_service.is_chain_valid()
            
            if not validation.is_valid:
                logger.error(f"Imported chain is invalid: {validation.issues}")
                return False
            
            # Replace current chain
            self.chain = imported_chain
            self.pending_transactions = []
            self.nodes = set(chain_data.get("nodes", []))
            
            # Save to database
            if self.db:
                # Clear existing data
                self.db.query(BlockchainTransactionModel).delete()
                self.db.query(BlockModel).delete()
                self.db.commit()
                
                # Save imported chain
                for block in self.chain:
                    self._save_block_to_db(block)
            
            logger.info(f"Chain imported successfully with {len(self.chain)} blocks")
            return True
            
        except Exception as e:
            logger.error(f"Error importing chain: {str(e)}")
            return False

# Global blockchain service instance (lazy initialization)
_blockchain_service = None

def get_blockchain_service(db: Session = None) -> BlockchainService:
    """Get or create blockchain service instance."""
    global _blockchain_service
    
    if _blockchain_service is None:
        _blockchain_service = BlockchainService(db)
    
    return _blockchain_service

async def create_blockchain_transaction(
    transaction_type: TransactionType,  # Use TransactionType enum
    user_id: str,
    data: Dict[str, Any],
    db: Session = None,
    **kwargs
) -> BlockchainTransaction:
    """Create blockchain transaction (global function)."""
    service = get_blockchain_service(db)
    return service.create_transaction(transaction_type, user_id, data, **kwargs)