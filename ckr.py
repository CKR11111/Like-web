import json
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import binascii
import requests
import jwt
from datetime import datetime
import my_pb2
import output_pb2
import like_pb2
import like_count_pb2
import uid_generator_pb2
import logging
from google.protobuf.json_format import MessageToJson
import urllib3
import sys
import os

# SSL warnings disable करें
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV = b'6oyZDr22E3ychjM%'
MAX_RETRIES = 3
RETRY_DELAY = 2

class FreeFireAutoLiker:
    def __init__(self, max_workers=10):  # 10 threads by default
        self.max_workers = max_workers
        self.accounts = []
        self.tokens = []
        
    def load_accounts(self, filename="accounts.json"):
        """Load accounts from JSON file"""
        try:
            if not os.path.exists(filename):
                print(f"❌ Error: {filename} file not found!")
                return False
                
            with open(filename, "r") as f:
                self.accounts = json.load(f)
            logger.info(f"✅ Loaded {len(self.accounts)} accounts from {filename}")
            return True
        except Exception as e:
            logger.error(f"❌ Error loading accounts: {e}")
            return False
    
    def encrypt_message(self, plaintext):
        """Encrypt message using AES CBC"""
        try:
            cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
            padded_message = pad(plaintext, AES.block_size)
            encrypted_message = cipher.encrypt(padded_message)
            return binascii.hexlify(encrypted_message).decode('utf-8')
        except Exception as e:
            logger.error(f"🔒 Encryption error: {e}")
            return None

    def create_protobuf(self, uid):
        """Create protobuf for UID"""
        try:
            message = uid_generator_pb2.uid_generator()
            message.saturn_ = int(uid)
            message.garena = 1
            return message.SerializeToString()
        except Exception as e:
            logger.error(f"📦 Error creating uid protobuf: {e}")
            return None

    def get_base_url(self, region, endpoint=""):
        """Get base URL based on region"""
        if region == "IND":
            base_url = "https://client.ind.freefiremobile.com"
        elif region in {"BR", "US", "SAC", "NA"}:
            base_url = "https://client.us.freefiremobile.com"
        else:
            base_url = "https://clientbp.ggblueshark.com"
        
        if endpoint:
            return f"{base_url}/{endpoint}"
        return base_url

    def get_player_info(self, target_uid, region, token):
        """Get player information including nickname and like count"""
        try:
            # Create protobuf for player info
            protobuf_data = self.create_protobuf(target_uid)
            if protobuf_data is None:
                return None
            
            encrypted_uid = self.encrypt_message(protobuf_data)
            if encrypted_uid is None:
                return None

            # Get URL for region
            url = self.get_base_url(region, "GetPlayerPersonalShow")

            edata = bytes.fromhex(encrypted_uid)
            headers = {
                'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
                'Connection': "Keep-Alive",
                'Accept-Encoding': "gzip",
                'Authorization': f"Bearer {token}",
                'Content-Type': "application/x-www-form-urlencoded",
                'Expect': "100-continue",
                'X-Unity-Version': "2018.4.11f1",
                'X-GA': "v1 1",
                'ReleaseVersion': "OB53"
            }

            response = requests.post(url, data=edata, headers=headers, verify=False, timeout=10)
            
            if response.status_code == 200:
                # Decode protobuf response
                hex_data = response.content.hex()
                binary = bytes.fromhex(hex_data)
                
                items = like_count_pb2.Info()
                items.ParseFromString(binary)
                
                # Convert to JSON for easy parsing
                json_data = MessageToJson(items)
                data = json.loads(json_data)
                
                account_info = data.get('AccountInfo', {})
                nickname = account_info.get('PlayerNickname', 'Unknown')
                likes = int(account_info.get('Likes', 0))
                uid = int(account_info.get('UID', 0))
                
                return {
                    'nickname': nickname,
                    'likes': likes,
                    'uid': uid,
                    'success': True
                }
            else:
                logger.error(f"❌ Failed to get player info. Status: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting player info: {e}")
            return None
    
    def get_token_with_retry(self, uid, password):
        """Get OAuth token with retry mechanism"""
        oauth_url = "https://100067.connect.garena.com/oauth/guest/token/grant"
        payload = {
            'uid': uid,
            'password': password,
            'response_type': "token",
            'client_type': "2",
            'client_secret': "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
            'client_id': "100067"
        }
        headers = {
            'User-Agent': "GarenaMSDK/4.0.19P9(SM-M526B ;Android 13;pt;BR;)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip"
        }

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"🔑 Attempt {attempt + 1} to get token for UID: {uid}")
                oauth_response = requests.post(oauth_url, data=payload, headers=headers, timeout=10)
                
                if oauth_response.status_code == 200:
                    oauth_data = oauth_response.json()
                    if 'access_token' in oauth_data and 'open_id' in oauth_data:
                        logger.info(f"✅ Successfully got OAuth token for UID: {uid}")
                        return oauth_data
                    else:
                        logger.warning(f"⚠️ OAuth response missing required fields for UID: {uid}")
                else:
                    logger.warning(f"⚠️ OAuth API returned HTTP {oauth_response.status_code} for UID: {uid}")
                    
            except requests.RequestException as e:
                logger.warning(f"⚠️ Request exception on attempt {attempt + 1} for UID {uid}: {str(e)}")
            
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        
        logger.error(f"❌ All {MAX_RETRIES} attempts failed for UID: {uid}")
        return None

    def major_login_with_retry(self, access_token, open_id):
        """Perform major login with retry mechanism"""
        platform_type = 4  # Guest accounts use platform 4

        for attempt in range(MAX_RETRIES):
            try:
                game_data = my_pb2.GameData()
                game_data.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                game_data.game_name = "free fire"
                game_data.game_version = 1
                game_data.version_code = "1.118.1"
                game_data.os_info = "Android OS 9 / API-28 (PI/rel.cjw.20220518.114133)"
                game_data.device_type = "Handheld"
                game_data.network_provider = "Verizon Wireless"
                game_data.connection_type = "WIFI"
                game_data.screen_width = 1280
                game_data.screen_height = 960
                game_data.dpi = "240"
                game_data.cpu_info = "ARMv7 VFPv3 NEON VMH | 2400 | 4"
                game_data.total_ram = 5951
                game_data.gpu_name = "Adreno (TM) 640"
                game_data.gpu_version = "OpenGL ES 3.0"
                game_data.user_id = "Google|74b585a9-0268-4ad3-8f36-ef41d2e53610"
                game_data.ip_address = "172.190.111.97"
                game_data.language = "en"
                game_data.open_id = open_id
                game_data.access_token = access_token
                game_data.platform_type = platform_type
                game_data.field_99 = str(platform_type)
                game_data.field_100 = str(platform_type)

                serialized_data = game_data.SerializeToString()
                encrypted_data = self.encrypt_message(serialized_data)
                if not encrypted_data:
                    continue

                hex_encrypted_data = encrypted_data
                url = "https://loginbp.ggblueshark.com/MajorLogin"
                headers = {
                    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
                    "Connection": "Keep-Alive",
                    "Accept-Encoding": "gzip",
                    "Content-Type": "application/octet-stream",
                    "Expect": "100-continue",
                    "X-Unity-Version": "2018.4.11f1",
                    "X-GA": "v1 1",
                    "ReleaseVersion": "OB53"
                }
                edata = bytes.fromhex(hex_encrypted_data)

                logger.info(f"🔄 Attempt {attempt + 1} for MajorLogin")
                response = requests.post(url, data=edata, headers=headers, verify=False, timeout=10)

                if response.status_code == 200:
                    data_dict = None
                    try:
                        example_msg = output_pb2.Garena_420()
                        example_msg.ParseFromString(response.content)
                        data_dict = {field.name: getattr(example_msg, field.name)
                                     for field in example_msg.DESCRIPTOR.fields
                                     if field.name not in ["binary", "binary_data", "Garena420"]}
                    except Exception:
                        try:
                            data_dict = response.json()
                        except ValueError:
                            continue

                    if data_dict and "token" in data_dict:
                        token_value = data_dict["token"]
                        try:
                            decoded_token = jwt.decode(token_value, options={"verify_signature": False})
                            
                            # Format the exp date
                            exp_timestamp = decoded_token.get("exp")
                            if exp_timestamp:
                                exp_date = datetime.fromtimestamp(exp_timestamp).strftime("%Y-%m-%d %H:%M:%S")
                                decoded_token["exp_date"] = exp_date
                            
                            return token_value
                        except Exception as e:
                            logger.warning(f"⚠️ JWT decode failed: {str(e)}")
                            continue
                    
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    
            except requests.RequestException as e:
                logger.warning(f"⚠️ Request failed for MajorLogin, attempt {attempt + 1}: {str(e)}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                continue

        return None

    def generate_token_for_account(self, account):
        """Generate JWT token for a single account"""
        uid = account.get('uid')
        password = account.get('password')
        
        if not uid or not password:
            logger.error("❌ Account missing uid or password")
            return None
        
        # Get OAuth token
        oauth_data = self.get_token_with_retry(uid, password)
        if not oauth_data:
            return None

        access_token = oauth_data['access_token']
        open_id = oauth_data['open_id']

        # Perform major login
        token = self.major_login_with_retry(access_token, open_id)
        if token:
            logger.info(f"✅ Successfully generated token for UID: {uid}")
            return {
                'uid': uid,
                'token': token,
                'original_account': account
            }
        else:
            logger.error(f"❌ Failed to generate token for UID: {uid}")
            return None

    def generate_all_tokens(self):
        """Generate tokens for all accounts using thread pool"""
        print(f"\n🔑 Generating tokens for {len(self.accounts)} accounts using {self.max_workers} threads...")
        
        self.tokens = []
        completed = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_account = {
                executor.submit(self.generate_token_for_account, account): account 
                for account in self.accounts
            }
            
            for future in as_completed(future_to_account):
                account = future_to_account[future]
                try:
                    token_data = future.result()
                    if token_data:
                        self.tokens.append(token_data)
                        completed += 1
                        print(f"✅ [{completed}/{len(self.accounts)}] Token generated for UID: {account.get('uid')}")
                    else:
                        print(f"❌ Failed to generate token for UID: {account.get('uid')}")
                except Exception as e:
                    print(f"❌ Error generating token for account {account.get('uid')}: {e}")
        
        print(f"\n✅ Successfully generated {len(self.tokens)} tokens out of {len(self.accounts)} accounts")
        return self.tokens

    def create_like_protobuf(self, user_id, region):
        """Create protobuf message for like"""
        try:
            message = like_pb2.like()
            message.uid = int(user_id)
            message.region = region
            return message.SerializeToString()
        except Exception as e:
            logger.error(f"📦 Error creating like protobuf: {e}")
            return None

    def send_like_request(self, token_data, target_uid, region, index, total):
        """Send like request for a single token"""
        try:
            # Create protobuf message
            protobuf_message = self.create_like_protobuf(target_uid, region)
            if not protobuf_message:
                return False

            # Encrypt the message
            encrypted_data = self.encrypt_message(protobuf_message)
            if not encrypted_data:
                return False

            # Get URL for region
            url = self.get_base_url(region, "LikeProfile")

            # Prepare request
            edata = bytes.fromhex(encrypted_data)
            headers = {
                'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
                'Connection': "Keep-Alive",
                'Accept-Encoding': "gzip",
                'Authorization': f"Bearer {token_data['token']}",
                'Content-Type': "application/x-www-form-urlencoded",
                'Expect': "100-continue",
                'X-Unity-Version': "2018.4.11f1",
                'X-GA': "v1 1",
                'ReleaseVersion': "OB53"
            }

            # Send request
            response = requests.post(url, data=edata, headers=headers, verify=False, timeout=10)
            
            if response.status_code == 200:
                print(f"✅ [{index}/{total}] Like sent from UID: {token_data['uid']} to target: {target_uid}")
                return True
            else:
                print(f"❌ [{index}/{total}] Like failed (HTTP {response.status_code}) from UID: {token_data['uid']}")
                return False

        except Exception as e:
            print(f"❌ [{index}/{total}] Error from UID {token_data['uid']}: {e}")
            return False

    def send_likes(self, target_uid, region):
        """Send likes to target UID from all tokens using thread pool"""
        if not self.tokens:
            print("❌ No tokens available. Please generate tokens first.")
            return 0, 0
        
        print(f"\n🚀 Sending likes to UID: {target_uid} in region: {region}")
        print(f"📊 Using {len(self.tokens)} tokens with {self.max_workers} parallel threads...")
        print("-" * 60)
        
        successful_likes = 0
        failed_likes = 0
        
        # Create a list of arguments for each task
        tasks = []
        for i, token_data in enumerate(self.tokens, 1):
            tasks.append((token_data, target_uid, region, i, len(self.tokens)))
        
        # Execute tasks in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for task in tasks:
                future = executor.submit(self.send_like_request, *task)
                futures.append(future)
            
            # Wait for all tasks to complete
            for future in as_completed(futures):
                try:
                    success = future.result()
                    if success:
                        successful_likes += 1
                    else:
                        failed_likes += 1
                except Exception as e:
                    print(f"❌ Error processing like: {e}")
                    failed_likes += 1
        
        print("-" * 60)
        return successful_likes, failed_likes

    def show_progress_bar(self, iteration, total, prefix='', suffix='', length=50, fill='█'):
        """Display progress bar"""
        percent = ("{0:.1f}").format(100 * (iteration / float(total)))
        filled_length = int(length * iteration // total)
        bar = fill * filled_length + '-' * (length - filled_length)
        print(f'\r{prefix} |{bar}| {percent}% {suffix}', end='\r')
        if iteration == total: 
            print()

    def run(self, target_uid, region):
        """Main method to run the entire process"""
        print("🔥 FREE FIRE AUTO LIKER 🔥")
        print("Developed by: t.me/danger_ff_like")
        print("=" * 60)
        
        # Load accounts
        if not self.load_accounts():
            return
        
        # Generate tokens
        tokens = self.generate_all_tokens()
        if not tokens:
            print("❌ No tokens generated. Exiting.")
            return
        
        print("\n" + "=" * 60)
        print("🎯 PLAYER INFORMATION")
        print("=" * 60)
        
        # Get player info before sending likes
        print("📡 Getting player information...")
        first_token = tokens[0]['token'] if tokens else None
        if first_token:
            player_info_before = self.get_player_info(target_uid, region, first_token)
            if player_info_before:
                print(f"👤 Nickname: {player_info_before['nickname']}")
                print(f"🆔 UID: {player_info_before['uid']}")
                print(f"❤️  Current Likes: {player_info_before['likes']}")
                print("=" * 60)
                
                # Wait for user confirmation
                input("\n⚠️  Press Enter to start sending likes...")
                print("\n" + "=" * 60)
                print("🚀 STARTING LIKE BOMBING")
                print("=" * 60)
                
                # Send likes
                successful, failed = self.send_likes(target_uid, region)
                
                # Wait a bit for server to process
                print("\n⏳ Waiting for server to process likes...")
                time.sleep(5)
                
                # Get player info after sending likes
                print("\n📡 Getting updated player information...")
                player_info_after = self.get_player_info(target_uid, region, first_token)
                
                if player_info_after:
                    likes_before = player_info_before['likes']
                    likes_after = player_info_after['likes']
                    likes_added = likes_after - likes_before
                    
                    print("\n" + "=" * 60)
                    print("📊 FINAL RESULTS")
                    print("=" * 60)
                    print(f"👤 Player: {player_info_after['nickname']}")
                    print(f"🆔 UID: {player_info_after['uid']}")
                    print(f"❤️  Likes Before: {likes_before}")
                    print(f"❤️  Likes After: {likes_after}")
                    print(f"✅ Likes Added: {likes_added}")
                    print("-" * 60)
                    print(f"🎯 Attempted Likes: {successful + failed}")
                    print(f"✅ Successful Likes: {successful}")
                    print(f"❌ Failed Likes: {failed}")
                    
                    success_rate = (successful/(successful+failed)*100) if (successful+failed) > 0 else 0
                    if success_rate > 80:
                        success_display = f"✅ {success_rate:.1f}%"
                    elif success_rate > 50:
                        success_display = f"⚠️  {success_rate:.1f}%"
                    else:
                        success_display = f"❌ {success_rate:.1f}%"
                    
                    print(f"📈 Success Rate: {success_display}")
                    print("=" * 60)
                    
                    # Save results to file
                    results = {
                        'player_nickname': player_info_after['nickname'],
                        'player_uid': player_info_after['uid'],
                        'region': region,
                        'likes_before': likes_before,
                        'likes_after': likes_after,
                        'likes_added': likes_added,
                        'attempted_likes': successful + failed,
                        'successful_likes': successful,
                        'failed_likes': failed,
                        'success_rate': success_rate,
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'accounts_used': len(tokens)
                    }
                    
                    with open('likes_results.json', 'w') as f:
                        json.dump(results, f, indent=2)
                    
                    print(f"\n💾 Results saved to 'likes_results.json'")
                    
                else:
                    print("❌ Failed to get player information after sending likes")
            else:
                print("❌ Failed to get player information")
                return
        else:
            print("❌ No valid tokens available")

def main():
    print("\n" + "="*60)
    print("🔥 FREE FIRE AUTO LIKER v2.0 🔥")
    print("="*60)
    
    # Configuration
    TARGET_UID = input("\n🎯 Enter target UID: ").strip()
    if not TARGET_UID:
        print("❌ Error: Target UID is required")
        return
    
    print("\n🌍 Available Regions:")
    print("   IND  - India")
    print("   BR   - Brazil")
    print("   US   - United States")
    print("   SAC  - South America")
    print("   NA   - North America")
    print("   BD   - Bangladesh")
    print("   Other - All other regions")
    
    REGION = input("\n🌍 Enter region: ").strip().upper()
    
    valid_regions = ["IND", "BR", "US", "SAC", "NA", "BD"]
    if REGION not in valid_regions:
        print(f"⚠️  Using default server for region: {REGION}")
        REGION = "OTHER"
    
    print(f"\n🔧 Configuration:")
    print(f"   Target UID: {TARGET_UID}")
    print(f"   Region: {REGION}")
    print(f"   Threads: 10")
    print(f"   Accounts File: accounts.json")
    
    confirm = input("\n⚠️  Continue? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ Operation cancelled")
        return
    
    # Create and run auto liker
    auto_liker = FreeFireAutoLiker(max_workers=10)
    auto_liker.run(TARGET_UID, REGION)
    
    print("\n" + "="*60)
    print("🎉 Operation Completed!")
    print("="*60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")