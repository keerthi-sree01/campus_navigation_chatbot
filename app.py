from flask import Flask, request, jsonify, render_template
import re
import difflib
import math
import ollama
import os
import urllib.parse

app = Flask(__name__)

# Structured campus data with coordinates
campus_data = {
    "gate": {"lat": 17.05973, "lng": 81.86922, "description": "Main campus entrance"},
    "globe": {"lat": 17.05997, "lng": 81.86928, "description": "Globe monument near entrance"},
    "main block parking": {"lat": 17.05957, "lng": 81.86877, "description": "Parking near main block"},
    "parking 2": {"lat": 17.06213, "lng": 81.86849, "aliases": ["fc"], "description": "Parking near food court"},
    "atm": {"lat": 17.06000, "lng": 81.86913, "description": "ATM machine location"},
    "main block": {"lat": 17.05975, "lng": 81.86875, "description": "Main academic building"},
    "saraswati devi": {"lat": 17.06026, "lng": 81.86875, "description": "Saraswati Devi statue"},
    "amphitheatre": {"lat": 17.06055, "lng": 81.86902, "description": "Open-air amphitheater"},
    "vishwesaraya block": {"lat": 17.06089, "lng": 81.86833, "description": "Engineering department building"},
    "juice shop": {"lat": 17.06146, "lng": 81.86780, "description": "Juice and snack bar"},
    "food stalls": {"lat": 17.06141, "lng": 81.86795, "description": "Street food vendors"},
    "food court": {"lat": 17.06148, "lng": 81.86780, "description": "Main food court area"},
    "Stationery shop": {"lat": 17.06153, "lng": 81.86790, "description": "Stationery and supplies store"},
    "mechanical labs": {"lat": 17.06434, "lng": 81.86786, "description": "Mechanical engineering laboratories"},
    "boys mess": {"lat": 17.06179, "lng": 81.86716, "description": "Boys hostel dining hall"},
    "girls hostel": {"lat": 17.06202, "lng": 81.86674, "description": "Girls accommodation block"},
    "basketball court": {"lat": 17.06213, "lng": 81.86769, "description": "Basketball playing area"},
    "football court": {"lat": 17.06259, "lng": 81.86766, "description": "Football/soccer field"},
    "mining block": {"lat": 17.06284, "lng": 81.86721, "description": "Mining engineering department"},
    "bamboos": {"lat": 17.06223, "lng": 81.86861, "description": "Bamboo garden area"},
    "yummpys": {"lat": 17.06323, "lng": 81.86791, "aliases": ["yummy"], "description": "Yummpy's snack shop"},
    "boys hostel": {"lat": 17.06313, "lng": 81.86563, "description": "Boys accommodation block"},
    "saibaba temple": {"lat": 17.06331, "lng": 81.86706, "description": "Saibaba temple on campus"},
    "pharmacy block": {"lat": 17.06360, "lng": 81.86576, "description": "Pharmacy department building"},
    "library": {"lat": 17.06410, "lng": 81.86618, "description": "Main campus library", "hours": "8AM-10PM"},
    "rk block": {"lat": 17.06426, "lng": 81.86590, "description": "RK academic block"},
    "central food court": {"lat": 17.06459, "lng": 81.86744, "aliases": ["cfc"], "description": "Central dining area"},
    "diploma block": {"lat": 17.06513, "lng": 81.86574, "description": "Diploma studies building"},
    "international boys hostel": {"lat": 17.06584, "lng": 81.86564, "description": "Hostel for international students"},
    "cricket ground": {"lat": 17.06493, "lng": 81.86880, "description": "Cricket playing field"},
    "bus ground": {"lat": 17.06479, "lng": 81.86598, "description": "Bus parking and pickup area"},
    "automobile engineering lab": {"lat": 17.06449, "lng": 81.86969, "description": "Automotive engineering lab"},
    "lakepond": {"lat": 17.06875, "lng": 81.86769, "description": "Lake and pond area"},
    "cv raman block": {"lat": 17.06846, "lng": 81.86727, "description": "CV Raman science block"},
    "spicehub": {"lat": 17.06896, "lng": 81.86838, "description": "SpiceHub food court"},
    "giet parking 3": {"lat": 17.06936, "lng": 81.86837, "description": "Parking area near SpiceHub"},
    "degree block": {"lat": 17.07090, "lng": 81.86853, "description": "Degree programs building"},
    "events ground": {"lat": 17.07154, "lng": 81.86830, "description": "Events and festival ground"},
    "lake": {"lat": 17.07146, "lng": 81.86981, "description": "Main campus lake"}
}

# Create alias mapping
alias_mapping = {}
for name, data in campus_data.items():
    aliases = data.get("aliases", [])
    for alias in aliases:
        alias_mapping[alias.lower()] = name
    alias_mapping[name.lower()] = name

# Precompute all location names for fuzzy matching
all_location_names = list(campus_data.keys()) + list(alias_mapping.keys())

def find_location(location_str):
    """Find location in database using name or alias with fuzzy matching"""
    if not location_str or location_str.strip() == "":
        return None
        
    location_str = location_str.lower().strip()
    
    # 1. Check direct match
    if location_str in alias_mapping:
        return alias_mapping[location_str]
    
    # 2. Check for similar matches
    matches = [name for name in campus_data.keys() if location_str in name.lower()]
    if matches:
        return matches[0]
    
    # 3. Try partial matches
    for name in campus_data.keys():
        if location_str in name.lower().replace(" ", ""):
            return name
            
    # 4. Fuzzy matching using difflib
    matches = difflib.get_close_matches(location_str, all_location_names, n=1, cutoff=0.5)
    if matches:
        return alias_mapping.get(matches[0].lower(), matches[0])
    
    return None

def calculate_distance(start, end):
    """Calculate distance using Haversine formula (in meters)"""
    # Convert decimal degrees to radians
    lat1, lon1 = math.radians(campus_data[start]['lat']), math.radians(campus_data[start]['lng'])
    lat2, lon2 = math.radians(campus_data[end]['lat']), math.radians(campus_data[end]['lng'])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    # Radius of earth in meters (6371 km)
    return 6371000 * c

def generate_directions(start, end):
    """Generate detailed directions with properly formatted Google Maps link"""
    if start == end:
        return f"🚶 You're already at {start.capitalize()}!"
    
    start_coords = f"{campus_data[start]['lat']},{campus_data[start]['lng']}"
    end_coords = f"{campus_data[end]['lat']},{campus_data[end]['lng']}"
    
    # Properly formatted Google Maps URL
    maps_url = (
        f"https://www.google.com/maps/dir/?api=1&"
        f"origin={start_coords}&"
        f"destination={end_coords}&"
        "travelmode=walking"
    )
    
    distance = calculate_distance(start, end)
    walking_time = distance / 67  # 67 meters per minute (average walking speed)
    
    # Create directions with steps
    directions = [
        f"🚶 Directions from {start.capitalize()} to {end.capitalize()}:",
        f"📍 Distance: Approximately {distance:.0f} meters",
        f"⏱️ Walking time: {max(1, int(walking_time))} minutes",
        f"🗺️ [Open in Google Maps]({maps_url})"
    ]
    
    # Add route guidance based on distance
    if distance < 100:
        directions.append(f"\n🔍 {end.capitalize()} is very close to {start.capitalize()} - you should see it nearby!")
    else:
        # Calculate bearing for cardinal direction
        lat1 = math.radians(campus_data[start]['lat'])
        lon1 = math.radians(campus_data[start]['lng'])
        lat2 = math.radians(campus_data[end]['lat'])
        lon2 = math.radians(campus_data[end]['lng'])
        
        y = math.sin(lon2-lon1) * math.cos(lat2)
        x = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(lon2-lon1)
        bearing = math.degrees(math.atan2(y, x))
        
        # Convert bearing to cardinal direction
        cardinals = ["North", "North-East", "East", "South-East", "South", "South-West", "West", "North-West"]
        idx = round(bearing / 45) % 8
        cardinal_dir = cardinals[idx]
        
        directions.append(f"\n🧭 Head {cardinal_dir} from {start.capitalize()}")
    
    # Add destination info
    if "description" in campus_data[end]:
        directions.append(f"\nℹ️ About this location: {campus_data[end]['description']}")
    
    if "hours" in campus_data[end]:
        directions.append(f"\n🕒 Hours: {campus_data[end]['hours']}")
    
    return "\n".join(directions)

def get_food_locations():
    """Return all food-related locations with emojis"""
    food_spots = {
        "food court": "🍽️ Main food court area",
        "central food court": "🍕 Central dining area (CFC)",
        "spicehub": "🌶️ SpiceHub food court",
        "juice shop": "🍹 Juice and snack bar",
        "food stalls": "🍢 Street food vendors",
        "yummpys": "🍔 Yummpy's snack shop"
    }
    return "\n".join([f"- {name.capitalize()}: {desc}" for name, desc in food_spots.items()])

def get_sports_locations():
    """Return all sports facilities with emojis"""
    sports = {
        "basketball court": "🏀 Basketball playing area",
        "football court": "⚽ Football/soccer field",
        "cricket ground": "🏏 Cricket playing field",
        "events ground": "🏟️ Events and festival ground"
    }
    return "\n".join([f"- {name.capitalize()}: {desc}" for name, desc in sports.items()])

def get_prayer_locations():
    """Return prayer locations with emojis"""
    prayer = {
        "saibaba temple": "🛕 Saibaba temple on campus",
        "saraswati devi": "🙏 Saraswati Devi statue"
    }
    return "\n".join([f"- {name.capitalize()}: {desc}" for name, desc in prayer.items()])

def generate_stationery_directions():
    """Special function for stationery shop directions with proper link"""
    start = "gate"
    end = "Stationery shop"
    
    if end not in campus_data or start not in campus_data:
        return "Couldn't find stationery shop location information."
    
    # Generate proper Google Maps URL
    start_coords = f"{campus_data[start]['lat']},{campus_data[start]['lng']}"
    end_coords = f"{campus_data[end]['lat']},{campus_data[end]['lng']}"
    maps_url = (
        f"https://www.google.com/maps/dir/?api=1&"
        f"origin={start_coords}&"
        f"destination={end_coords}&"
        "travelmode=walking"
    )
    
    distance = calculate_distance(start, end)
    walking_time = distance / 67
    
    # Create detailed response
    return (
        "📚 You're looking for a place to buy a book! 📖\n\n"
        "You can find the Stationery shop near the Main Block building 🔵. "
        "It's a convenient spot to grab your favorite books, stationery supplies, and more! 🎉\n\n"
        "Here are the step-by-step directions:\n\n"
        "**From the Gate:**\n"
        "1. Head towards the Globe monument 🌍\n"
        "2. Turn left towards the Main Block building 🔵\n"
        "3. Walk straight for about 150 meters 👣\n"
        "4. You'll find the Stationery shop on your right-hand side 📚\n\n"
        f"**Approximate distance:** {distance:.0f} meters 📍\n"
        f"**Walking time:** {max(1, int(walking_time))} minutes ⏰\n\n"
        f"🗺️ [Open in Google Maps]({maps_url})\n\n"
        "Hope this helps! 😊"
    )

def has_whole_word(keywords, message):
    return any(re.search(rf"\b{re.escape(word)}\b", message) for word in keywords)

def process_special_queries(user_message):
    """Handle special queries with strict keyword detection"""
    user_message = user_message.lower()

    # Stationery / Books
    if has_whole_word(["book", "books", "stationery", "notebook", "pen", "pencil", "xerox", "photocopy", "buy book"], user_message):
        return generate_stationery_directions()
    
    # Food
    if has_whole_word(["food", "eat", "hungry", "restaurant", "canteen", "snack", "dine", "dining", "juice", "spicehub", "yummpy"], user_message):
        return (
            "🍴 Here are all food locations on campus:\n\n"
            f"{get_food_locations()}\n\n"
            "Ask 'How to get to [location]?' for directions to any of these!"
        )
    
    # Prayer
    if has_whole_word(["pray", "temple", "worship", "god", "religious", "statue", "saibaba", "saraswati"], user_message):
        return (
            "🙏 Here are prayer locations on campus:\n\n"
            f"{get_prayer_locations()}\n\n"
            "Ask for directions to any of these!"
        )

    # Sports
    if has_whole_word(["play", "sports", "game", "basketball", "football", "cricket", "ground", "field", "court"], user_message):
        return (
            "🏅 Here are the sports facilities available on campus:\n\n"
            f"{get_sports_locations()}\n\n"
            "Ask for directions to any of these grounds!"
        )

    # Administrative / Fee / Transport Office
    if has_whole_word(["fee", "fees", "administrative", "admin block", "principal", "transport office", "admission", "pay", "tc", "scholarship"], user_message):
        return generate_directions("gate", "main block") + (
            "\n\n🧾 The Administrative Block is in the **Main Block (Ground Floor)**. "
            "You can visit here to:\n"
            "- Pay fees 💰\n"
            "- Submit transport or admission forms 🚌\n"
            "- Meet the principal or officials 📋\n"
        )

    return None


def generate_system_prompt():
    """Generate system prompt with campus information for Llama"""
    locations = "\n".join([f"- {name}: {data['description']}" for name, data in campus_data.items()])
    
    return (
        "You are a navigation assistant for GIET University. "
        "Use this campus location data to answer questions:\n\n"
        f"{locations}\n\n"
        "When asked for directions between two points, provide step-by-step directions, "
        "approximate distance, and walking time. Always include a Google Maps link. "
        "Format responses with emojis and clear sections. For location information, "
        "provide description and nearby places. For campus map requests, provide a link. "
        "Be friendly and helpful. If a question isn't about campus navigation, "
        "politely decline to answer."
    )

def query_llama(user_message, conversation_history=[]):
    """Query Llama model with campus context"""
    system_prompt = generate_system_prompt()
    
    messages = [
        {"role": "system", "content": system_prompt},
        *conversation_history[-3:],
        {"role": "user", "content": user_message}
    ]
    
    try:
        response = ollama.chat(
            model='llama3',
            messages=messages,
            options={'temperature': 0.3}
        )
        return response['message']['content']
    except Exception as e:
        print(f"Llama error: {str(e)}")
        return "I'm having trouble understanding. Could you please rephrase your question?"

def process_message(user_message):
    """Process user message with special handling for book/shopping queries"""
    # First check for special queries
    special_response = process_special_queries(user_message)
    if special_response:
        return special_response
        
    # Patterns for different types of queries
    from_to_pattern = r'(?:from|between)\s+(.+?)\s+(?:to|and)\s+(.+)'
    to_pattern = r'(?:to|for|towards|near|reach|get to|go to)\s+(.+)'
    where_pattern = r'(?:where(\'s| is)|find|locate|show me|how to get to|directions? to)\s+(.+)'
    info_pattern = r'(?:info|information|details|about|tell me about)\s+(.+)'
    help_pattern = r'(?:help|what can you do|options|features|commands)'
    map_pattern = r'(?:map|campus map|whole map|complete map)'
    simple_directions_pattern = r'(.+?)\s+to\s+(.+)'
    current_location_pattern = r'(?:where am i|my location|current location)'
    
    start = None
    end = None
    
    try:
        # Check for help request
        if re.search(help_pattern, user_message, re.IGNORECASE):
            return (
                "🌟 I'm your campus navigation assistant! I can help with:\n"
                "- Directions between locations\n"
                "- Finding places (food courts, sports grounds, temples)\n"
                "- Information about locations\n"
                "- Campus map with all locations\n\n"
                "Try asking:\n"
                "- 'Where can I buy books?'\n"
                "- 'How to go to library?'\n"
                "- 'Directions from gate to main block'\n"
                "- 'Show me the campus map'"
            )
        
        # Check for map request
        if re.search(map_pattern, user_message, re.IGNORECASE):
            # Create Google Maps URL with all markers
            markers = "&markers=" + "|".join([f"{data['lat']},{data['lng']}" for data in campus_data.values()])
            map_url = f"https://www.google.com/maps?{markers}&q=17.05973,81.86922"
            return (
                "🗺️ Here's the complete campus map:\n"
                f"📍 [View Campus Map on Google Maps]({map_url})\n\n"
                "Key locations include:\n"
                "- " + "\n- ".join([name.capitalize() for name in list(campus_data.keys())[:10]]) + "\n...and more!"
            )
        
        # Check for location information request
        if info_match := re.search(info_pattern, user_message, re.IGNORECASE):
            loc_str = info_match.group(1).strip()
            location = find_location(loc_str)
            
            if location and location in campus_data:
                data = campus_data[location]
                # Create direct Google Maps link
                maps_url = f"https://www.google.com/maps/search/?api=1&query={data['lat']},{data['lng']}"
                
                response = f"ℹ️ Information about {location.capitalize()}:\n"
                response += f"- Description: {data['description']}\n"
                response += f"- 📍 [View on Google Maps]({maps_url})\n"
                
                if "hours" in data:
                    response += f"- Hours: {data['hours']}\n"
                
                # Find nearby locations
                nearby = []
                for other_name, other_data in campus_data.items():
                    if other_name != location:
                        dist = calculate_distance(location, other_name)
                        if dist < 200:  # within 200 meters
                            nearby.append((other_name, dist))
                
                if nearby:
                    response += "\n📍 Nearby locations:\n"
                    for name, dist in sorted(nearby, key=lambda x: x[1])[:3]:
                        response += f"- {name.capitalize()} ({dist:.0f}m)\n"
            else:
                response = f"❌ Sorry, I couldn't find information about '{loc_str}'"
            return response
        
        # Check for "where am I" request
        if re.search(current_location_pattern, user_message, re.IGNORECASE):
            # Create Google Maps URL with all markers
            markers = "&markers=" + "|".join([f"{data['lat']},{data['lng']}" for data in campus_data.values()])
            map_url = f"https://www.google.com/maps?{markers}&q=17.05973,81.86922"
            return (
                "📍 I can't determine your exact location, but here's the campus map:\n"
                f"🗺️ [View Campus Map on Google Maps]({map_url})\n\n"
                "You can ask:\n"
                "- 'Where is [place]' to find locations\n"
                "- 'Directions to [place]' for navigation"
            )
        
        # Check for "where is" request
        if where_match := re.search(where_pattern, user_message, re.IGNORECASE):
            # Handle different regex group positions
            loc_str = where_match.group(2) if where_match.group(2) else where_match.group(1)
            location = find_location(loc_str)
            
            if location and location in campus_data:
                data = campus_data[location]
                # Create direct Google Maps link
                maps_url = f"https://www.google.com/maps/search/?api=1&query={data['lat']},{data['lng']}"
                
                response = f"📍 {location.capitalize()} is located at:\n"
                response += f"- Description: {data['description']}\n"
                response += f"- 📍 [View on Google Maps]({maps_url})\n"
                
                # Find nearby locations
                nearby = []
                for other_name, other_data in campus_data.items():
                    if other_name != location:
                        dist = calculate_distance(location, other_name)
                        if dist < 200:  # within 200 meters
                            nearby.append((other_name, dist))
                
                if nearby:
                    response += "\n📍 Nearby locations:\n"
                    for name, dist in sorted(nearby, key=lambda x: x[1])[:3]:
                        response += f"- {name.capitalize()} ({dist:.0f}m)\n"
            else:
                response = f"❌ Sorry, I couldn't find '{loc_str}'"
            return response
        
        # Check for directions request patterns
        if from_to_match := re.search(from_to_pattern, user_message, re.IGNORECASE):
            start_str, end_str = from_to_match.groups()
            start = find_location(start_str)
            end = find_location(end_str)
        elif simple_match := re.search(simple_directions_pattern, user_message, re.IGNORECASE):
            start_str, end_str = simple_match.groups()
            start = find_location(start_str)
            end = find_location(end_str)
        elif to_match := re.search(to_pattern, user_message, re.IGNORECASE):
            end_str = to_match.group(1).strip()
            start = "gate"  # Default to main gate as starting point
            end = find_location(end_str)
        
        # Generate directions if we have both points
        if start and end:
            if end not in campus_data:
                return f"❌ Sorry, I couldn't find '{end}'"
            if start not in campus_data:
                return f"❌ Sorry, I couldn't find '{start}'"
            return generate_directions(start, end)
                
        # No pattern matched - use Llama
        return query_llama(user_message)
    
    except Exception as e:
        return f"❌ Sorry, I encountered an error: {str(e)}"

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat_handler():
    user_message = request.json['message']
    response = process_message(user_message)
    return jsonify({"response": response})

@app.route('/map')
def campus_map():
    return jsonify(campus_data)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
