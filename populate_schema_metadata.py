#!/usr/bin/env python3
"""
Populate schema_metadata table with comprehensive natural language
descriptions for EVERY column across ALL 11 tables.

This powers the RAG layer -- when a user asks a question, the system
embeds it and does similarity search against these descriptions to
find relevant columns and tables.
"""

import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "wargame_analysis",
    "user": "postgres",
    "password": "1311",
}

# =================================================================
# METADATA FOR EVERY COLUMN IN EVERY TABLE
# Each entry: (table, column, description, unit, typical_range,
#              related_columns, example_questions)
# =================================================================

METADATA = [
    # ==============================================================
    # TABLE 1: game
    # One row per complete wargame run
    # ==============================================================
    ("game", "game_id",
     "Unique integer identifier for each wargame session. Primary key. All other tables reference this to tie data back to a specific game run.",
     None, "1+",
     "force.game_id, platform_profile.game_id",
     "Which game session are we analysing? How many games have been played?"),

    ("game", "scenario_name",
     "Short human-readable name for the scenario being played in this wargame. Examples include 'Arabian Sea Confrontation' or 'Pacific Blockade'. Identifies the type of military situation being simulated.",
     None, None,
     None,
     "What scenario was played? What was the name of the last wargame?"),

    ("game", "scenario_objective",
     "Full text description of the overall mission objective for this game. Explains what each force is trying to achieve and the strategic context of the wargame. Critical for understanding the purpose of platform movements and tactical decisions.",
     None, None,
     "game_outcome",
     "What was the objective of the game? What was Blue force trying to accomplish? What were the victory conditions?"),

    ("game", "game_outcome",
     "Final result of the wargame. Indicates which force won or whether it was a draw or inconclusive. Determined by which force achieved its scenario objective.",
     None, "Blue won, Red won, Green won, Yellow won, inconclusive, draw",
     "scenario_objective",
     "Who won the game? What was the final outcome? Did Blue force achieve its objective?"),

    ("game", "weather_condition",
     "Overall weather conditions during the wargame. Affects visibility, sea state, radar performance, and aircraft operations. A single value representing the dominant weather pattern.",
     None, "Clear, Foggy, Stormy, Overcast, Rainy",
     "platform_telemetry_log.visibility_km, platform_telemetry_log.sea_state",
     "What was the weather during the game? Was it foggy? Did weather affect operations?"),

    ("game", "start_clock",
     "The integer clock tick value when the game began. Usually 0. All events, telemetry, and actions are timestamped relative to this starting tick.",
     "ticks", "0",
     "end_clock, clock_interval",
     "When did the game start? What was the first clock tick?"),

    ("game", "end_clock",
     "The integer clock tick value when the game ended. The difference between end_clock and start_clock, divided by clock_interval, gives the total number of logged time steps. Combined with tick duration, this tells you total game time.",
     "ticks", "1000-10000",
     "start_clock, clock_interval",
     "When did the game end? How long did the game last in ticks? What was the total game duration?"),

    ("game", "clock_interval",
     "Number of ticks between each telemetry log entry. If 1, logs are recorded at every single tick. If 5, logs are recorded every 5th tick. Determines the temporal granularity of all recorded data.",
     "ticks", "1-10",
     "start_clock, end_clock",
     "How often were logs recorded? What is the time resolution of the data?"),

    ("game", "game_start_real_time",
     "Real-world wall-clock timestamp when the game clock started. Used to convert any game clock tick into an actual date and time. Formula: real_time = game_start_real_time + (clock_tick * clock_interval) minutes.",
     None, None,
     "platform_telemetry_log.real_timestamp",
     "What real-world time did the game start? What date and time does tick 1000 correspond to?"),

    ("game", "date_played",
     "The calendar date on which this wargame was conducted. Used for record-keeping and to distinguish between multiple games played on different days.",
     None, None,
     None,
     "When was this game played? What date was the exercise conducted?"),

    ("game", "total_forces",
     "Total number of forces (teams/sides) participating in this wargame. Each force has its own commander, platforms, and objectives.",
     "count", "2-6",
     "force.force_id",
     "How many forces were in the game? How many sides participated?"),

    # ==============================================================
    # TABLE 2: force
    # One row per force (team/side) in the game
    # ==============================================================
    ("force", "force_id",
     "Unique integer identifier for each force. Primary key. Used throughout all tables to identify which team a platform, action, or detection belongs to.",
     None, "1-4",
     "platform_profile.force_id, platform_telemetry_log.force_id",
     "How many forces are there? List all force IDs."),

    ("force", "game_id",
     "Foreign key referencing the game this force belongs to. Links this force to a specific wargame session.",
     None, "1+",
     "game.game_id",
     "Which game does this force belong to?"),

    ("force", "force_name",
     "Human-readable name of the force. Standard NATO-style colour codes: Blue (typically friendly), Red (typically adversary), Green and Yellow (typically neutral or allied). Used throughout consolidated logs and reports for easy identification.",
     None, "Blue, Red, Green, Yellow",
     "main_consolidated_log.force_name",
     "Which forces were in the game? What is the name of force 2? Which force is the adversary?"),

    ("force", "commander_name",
     "Name of the officer commanding this force. Each force has a single overall commander who directs all platforms under that force.",
     None, None,
     None,
     "Who commanded Blue force? Who was the Red force commander? Who led the Green team?"),

    ("force", "total_platforms",
     "Total number of platforms (ships, aircraft, submarines) assigned to this force. Indicates the relative strength of each force.",
     "count", "5-7",
     "platform_profile.platform_id",
     "How many platforms does Blue have? Which force has the most platforms? How many ships does Red control?"),

    # ==============================================================
    # TABLE 3: platform_profile
    # One row per platform (ship, aircraft, or submarine)
    # ==============================================================
    ("platform_profile", "platform_id",
     "Unique integer identifier for each platform. Primary key. Every telemetry entry, action, message, and detection references this ID. Links to a specific ship, aircraft, or submarine.",
     None, "1-24",
     "platform_telemetry_log.platform_id, tactical_actions.platform_id",
     "How many platforms are there? What is platform 7?"),

    ("platform_profile", "force_id",
     "Foreign key identifying which force this platform belongs to. Determines the team allegiance of this platform.",
     None, "1-4",
     "force.force_id",
     "Which force does INS Vikramaditya belong to? How many platforms does Blue force have?"),

    ("platform_profile", "game_id",
     "Foreign key referencing the game session. Links this platform definition to a specific wargame.",
     None, "1+",
     "game.game_id",
     "Which game does this platform belong to?"),

    ("platform_profile", "platform_name",
     "Human-readable name of the platform. For ships, these are real or realistic naval vessel names like 'INS Vikramaditya', 'PNS Babur', 'FNS Djibouti'. For aircraft, names like 'Blue Hawk-1', 'Red Eagle-1'. Unique within a game.",
     None, None,
     "main_consolidated_log.platform_name",
     "What is the name of platform 5? What platforms does Blue force have? List all ship names."),

    ("platform_profile", "platform_type",
     "Classification of the platform. Three types: 'ship' (surface naval vessel), 'aircraft' (maritime patrol or combat aircraft), 'submarine' (underwater vessel). Determines which telemetry fields are relevant -- aircraft have altitude, submarines have depth, ships have neither.",
     None, "ship, aircraft, submarine",
     "main_consolidated_log.platform_type",
     "How many submarines does Red have? What type of platform is Blue Hawk-1? List all aircraft in the game. How many ships are in the game?"),

    ("platform_profile", "max_fuel_capacity",
     "Maximum fuel capacity of this platform in litres. Determines how far the platform can travel before needing resupply. Aircraft have 3200-4000 litres, large ships up to 8000 litres, submarines 900-1200 litres.",
     "litres", "900-8000",
     "platform_telemetry_log.fuel_level",
     "What is INS Vikramaditya's fuel capacity? Which platform has the most fuel? What is the range of Blue Hawk-1?"),

    ("platform_profile", "fuel_type",
     "Type of fuel used by this platform. Ships use 'Diesel', aircraft use 'Aviation Fuel', submarines use 'Diesel-Electric'. Affects consumption rate and operational patterns.",
     None, "Diesel, Aviation Fuel, Diesel-Electric",
     "max_fuel_capacity",
     "What fuel does INS Kalvari use? Which platforms use aviation fuel?"),

    ("platform_profile", "max_speed_knots",
     "Maximum speed capability of this platform measured in knots. Ships range from 25-32 knots, submarines 18-22 knots, aircraft 400-480 knots. Platforms rarely operate at max speed due to fuel consumption.",
     "knots", "18-480",
     "platform_telemetry_log.speed_knots",
     "What is the fastest platform? What is INS Kolkata's maximum speed? How fast can Blue Hawk-1 fly?"),

    ("platform_profile", "max_crew",
     "Maximum number of personnel this platform can carry. Carriers have up to 1600 crew, destroyers around 300, aircraft 8-12, submarines 35-44.",
     "personnel", "8-1600",
     "platform_telemetry_log.crew_count",
     "How many crew can INS Vikramaditya carry? What is the crew complement of PNS Babur?"),

    ("platform_profile", "radar_range_km",
     "Maximum detection range of this platform's radar system in kilometres. Aircraft have the longest radar range (350-450km) as they fly at high altitude. Ships range from 120-350km. Submarines have very short radar range (30-40km) and can only use radar when surfaced.",
     "km", "30-450",
     "platform_telemetry_log.radar_status, platform_telemetry_log.radar_range_active_km",
     "What is the radar range of Blue Hawk-1? Which platform has the best radar? Can submarines use radar underwater?"),

    ("platform_profile", "sonar_range_km",
     "Maximum detection range of this platform's sonar system in kilometres. Submarines have the best sonar (90-120km). Ships have moderate sonar (20-40km). Aircraft have no sonar (0km). Sonar works underwater and can detect submerged submarines that radar cannot see.",
     "km", "0-120",
     "platform_telemetry_log.sonar_status",
     "Which platform has the best sonar? Do aircraft have sonar? What is INS Kalvari's sonar range?"),

    ("platform_profile", "weapon_load",
     "Text description of weapons and armaments equipped on this platform. Includes missiles, torpedoes, guns, and defensive systems. Used for understanding combat capability.",
     None, None,
     "tactical_actions.action_type",
     "What weapons does INS Kolkata carry? Which platforms have torpedoes? What missiles does PNS Babur have?"),

    ("platform_profile", "initial_latitude",
     "Starting latitude position of this platform at tick 0. Decimal degrees, positive = north. Combined with initial_longitude gives the exact starting position on the map.",
     "degrees", "11-23",
     "initial_longitude, platform_telemetry_log.latitude",
     "Where did INS Vikramaditya start? What was the initial position of Blue force?"),

    ("platform_profile", "initial_longitude",
     "Starting longitude position of this platform at tick 0. Decimal degrees, positive = east. Combined with initial_latitude gives the exact starting position on the map.",
     "degrees", "43-68",
     "initial_latitude, platform_telemetry_log.longitude",
     "Where did PNS Babur start? Where were Red force platforms initially positioned?"),

    # ==============================================================
    # TABLE 4: platform_telemetry_log
    # One row per platform per clock tick -- the main data table
    # 120,024 rows (24 platforms x 5001 ticks)
    # ==============================================================
    ("platform_telemetry_log", "log_id",
     "Unique auto-incrementing identifier for each telemetry record. Primary key. Each row represents the complete state snapshot of one platform at one clock tick.",
     None, "1-120024",
     None,
     None),

    ("platform_telemetry_log", "game_id",
     "Foreign key linking this telemetry record to the game session.",
     None, "1+",
     "game.game_id",
     None),

    ("platform_telemetry_log", "platform_id",
     "Foreign key identifying which platform this telemetry belongs to. Join with platform_profile to get the platform name, type, and capabilities.",
     None, "1-24",
     "platform_profile.platform_id, platform_profile.platform_name",
     "Show telemetry for INS Vikramaditya. What was platform 7 doing at tick 1500?"),

    ("platform_telemetry_log", "force_id",
     "Foreign key identifying the force this platform belongs to. Duplicated from platform_profile for efficient querying without joins.",
     None, "1-4",
     "force.force_id, force.force_name",
     "Show all Blue force telemetry at tick 1000. Compare Red and Blue force movements."),

    ("platform_telemetry_log", "clock_tick",
     "Integer game clock value when this telemetry snapshot was recorded. Ranges from 0 (game start) to 5000 (game end). Each tick represents 1 minute of game time. This is the primary time axis for all analysis -- use it to track platform state over time, calculate durations, and correlate events across platforms.",
     "ticks", "0-5000",
     "real_timestamp",
     "What was INS Kolkata doing at tick 1000? Show me all events at tick 1500. What happened between tick 2000 and 3000?. Use this column for natural language time queries like yesterday, today, 1:00 PM, AM, PM, hours, minutes, and dates."),

    ("platform_telemetry_log", "real_timestamp",
     "Actual real-world date and time corresponding to this clock tick. Calculated as game_start_real_time + (clock_tick * 1 minute). Use this when the user asks questions using real time references like 'at noon' or 'during the first hour'.. Use this column for natural language time queries like yesterday, today, 1:00 PM, AM, PM, hours, minutes, and dates.",
     None, None,
     "clock_tick, game.game_start_real_time",
     "What happened at 12:00 PM? Show activity during the first hour. What time did the battle start?"),

    ("platform_telemetry_log", "latitude",
     "Current geographic latitude of the platform at this clock tick. Decimal degrees, positive values indicate North. Combined with longitude, this gives the platform's exact position on the map. Used for calculating distances between platforms, plotting movement tracks, and determining zone occupancy.",
     "degrees", "11-24",
     "longitude, platform_profile.initial_latitude",
     "Where was INS Vikramaditya at tick 2000? Plot the movement track of PNS Babur. How far did INS Kolkata travel?"),

    ("platform_telemetry_log", "longitude",
     "Current geographic longitude of the platform at this clock tick. Decimal degrees, positive values indicate East. Combined with latitude, this gives the platform's exact position on the map.",
     "degrees", "43-70",
     "latitude, platform_profile.initial_longitude",
     "Where was PNS Ghazi at tick 3000? Show all platform positions at tick 1500."),

    ("platform_telemetry_log", "speed_knots",
     "Speed of the platform at this clock tick measured in nautical knots. Ships cruise at 15-18 knots, submarines at 8-12 knots, aircraft at 300-400 knots. Speed increases during combat (28-30 knots for ships) and decreases when damaged or low on fuel. Higher speed burns more fuel exponentially.",
     "knots", "0-480",
     "fuel_consumed_interval, course_deg",
     "What was the average speed of INS Kolkata? How fast was PNS Babur going at tick 1500? When did Red ships speed up? Which platform was the fastest?"),

    ("platform_telemetry_log", "course_deg",
     "Direction of travel in compass degrees at this clock tick. 0 = North, 90 = East, 180 = South, 270 = West. Indicates the direction the platform is moving (not necessarily facing). Changes when the platform turns toward a new waypoint or takes evasive action.",
     "degrees", "0-360",
     "heading_deg, latitude, longitude",
     "What direction was PNS Babur heading at tick 1500? When did INS Talwar change course? Show course changes during the battle."),

    ("platform_telemetry_log", "heading_deg",
     "Direction the platform is physically facing in compass degrees. Usually close to course_deg but may differ during turns, crabbing in wind, or when a ship's weapons are oriented differently from its direction of travel.",
     "degrees", "0-360",
     "course_deg",
     "Was the ship turning at tick 2000? What was the heading difference during evasive manoeuvres?"),

    ("platform_telemetry_log", "altitude_meters",
     "Height above sea level in metres. Only meaningful for aircraft platforms -- ships and submarines always have altitude 0. Aircraft patrol at 3000-7000 metres and may descend when low on fuel or during attack runs.",
     "meters", "0-8000",
     "platform_profile.platform_type, depth_meters",
     "What altitude was Blue Hawk-1 flying at? How high were the aircraft during patrol? Did any aircraft descend during combat?"),

    ("platform_telemetry_log", "depth_meters",
     "Depth below the sea surface in metres. Only meaningful for submarine platforms -- ships and aircraft always have depth 0. Submarines cycle between surfaced (0m), periscope depth (~15m), and deep patrol (100-250m). When surfaced, submarines can use radar; when submerged, they rely on sonar. A submarine at depth cannot be detected by radar.",
     "meters", "0-250",
     "platform_profile.platform_type, sonar_status, radar_status",
     "How deep was INS Kalvari at tick 500? When was PNS Ghazi submerged? Were submarines surfaced during the battle? Show submarine depth profile over time."),

    ("platform_telemetry_log", "fuel_level",
     "Fuel remaining in the platform at this clock tick, measured in litres. Starts at max_fuel_capacity and decreases over time. Rate of decrease depends on speed (exponential relationship: fuel_rate * (speed/cruise_speed)^1.5), engine damage (1.4x multiplier), and platform type. When fuel drops below 15% of max capacity, a low fuel alert is triggered.",
     "litres", "0-8000",
     "fuel_consumed_interval, platform_profile.max_fuel_capacity",
     "How much fuel did INS Vikramaditya have at tick 3000? When did Blue Hawk-1 run low on fuel? Which platform consumed the most fuel? How much fuel was left at the end of the game?"),

    ("platform_telemetry_log", "fuel_consumed_interval",
     "Amount of fuel burned since the previous clock tick, measured in litres. This is the per-tick fuel consumption. Sum these values to get total fuel consumed over any time range. Higher speeds cause exponentially higher consumption. Damaged engines consume 1.4x more fuel.",
     "litres", "0.1-5.0",
     "fuel_level, speed_knots, engine_status",
     "How much fuel was used to cover 100km? What was the total fuel consumption for Blue force? What was the average fuel burn rate of INS Kolkata? How much fuel was burned during combat?"),

    ("platform_telemetry_log", "crew_count",
     "Number of personnel currently aboard the platform at this tick. Usually stays near max_crew but may decrease slightly due to casualties, transfers, or operational changes. Varies by about 10% over the game.",
     "personnel", "8-1600",
     "platform_profile.max_crew",
     "How many crew were on INS Talwar at tick 2000? Did any platform lose crew during combat?"),

    ("platform_telemetry_log", "radar_status",
     "Current state of the platform's radar system. 'On' means actively scanning and can detect targets. 'Standby' means powered but not emitting (used by surface ships between active scans). 'Off' means radar is not operational. Ships cycle radar On for 60-80 ticks then Standby for 15-20 ticks. Submarines can only use radar when surfaced (depth < 5m). Aircraft keep radar on for longer periods (100+ ticks).",
     None, "On, Off, Standby",
     "radar_range_active_km, platform_profile.radar_range_km",
     "When did Blue's carrier turn on radar? How often was PNS Babur's radar active? Were submarines using radar while submerged? What percentage of time was radar on for each platform?"),

    ("platform_telemetry_log", "radar_range_active_km",
     "The active radar detection range at this clock tick in kilometres. Equals the platform's max radar_range_km when radar_status is 'On', and 0 when radar is 'Off' or 'Standby'. Use this to determine if a platform could theoretically detect targets at a given distance.",
     "km", "0-450",
     "radar_status, platform_profile.radar_range_km",
     "What was INS Kolkata's active radar range when it detected PNS Babur? Which platform had the longest active radar reach?"),

    ("platform_telemetry_log", "sonar_status",
     "Current state of the platform's sonar system. 'On' means actively listening and can detect underwater targets. 'Off' means sonar is not operational. Submarines always have sonar on when submerged. Ships with sonar capability keep it on. Aircraft never have sonar.",
     None, "On, Off, Standby",
     "depth_meters, platform_profile.sonar_range_km",
     "Was INS Kalvari using sonar while submerged? Which platforms had sonar active? Did any ship turn off sonar?"),

    ("platform_telemetry_log", "weapon_status",
     "Current readiness state of the platform's weapon systems. 'Safe' during routine patrol, 'Armed' during combat readiness or when hull integrity is below 70%, 'Deployed' when weapons are actively being used. Blue and Red forces arm weapons during ticks 1400-2200 (combat phase).",
     None, "Armed, Safe, Deployed",
     "hull_integrity_pct, tactical_actions.action_type",
     "When did Blue force arm weapons? Were weapons armed during the engagement? Which platforms had weapons deployed?"),

    ("platform_telemetry_log", "engine_status",
     "Current condition of the platform's propulsion system. 'Normal' means operating correctly. 'Damaged' means reduced performance and 40% higher fuel consumption. 'Offline' means the platform cannot move (destroyed or fully disabled). Engine damage occurs from battle damage events.",
     None, "Normal, Damaged, Offline",
     "hull_integrity_pct, operational_status, fuel_consumed_interval",
     "Which platforms had engine damage? When did PNS Aslat's engines get damaged? Did engine damage affect fuel consumption?"),

    ("platform_telemetry_log", "hull_integrity_pct",
     "Structural integrity of the platform's hull as a percentage from 0 to 100. 100 means undamaged, 0 means destroyed/sunk. Decreases from scripted battle damage events. Below 50% triggers a critical hull damage alert. When it reaches 0, the platform is destroyed and all systems go offline. Key metric for tracking combat damage progression.",
     "percent", "0-100",
     "operational_status, engine_status, alert_flag",
     "How much damage did PNS Aslat take? When did the hull integrity drop? Which platforms were damaged during combat? Show hull integrity timeline for Red force ships."),

    ("platform_telemetry_log", "communication_status",
     "Status of the platform's communication systems. 'Online' means normal communications. 'Degraded' means partial communication capability (usually from battle damage). 'Offline' means no communications (destroyed platform). PNS Aslat's comms were degraded at tick 2500 before being destroyed at tick 3000.",
     None, "Online, Degraded, Offline",
     "operational_status",
     "Did any platform lose communications? When did PNS Aslat go silent? Which platforms had degraded comms?"),

    ("platform_telemetry_log", "operational_status",
     "Overall operational status of the platform. 'Active' means fully operational. 'Damaged' means still fighting but impaired (hull < 100%, engine damage). 'Destroyed' means the platform was sunk or shot down (hull = 0). 'Withdrawn' means the platform retreated from the battle area. This is the master status field for filtering operational vs non-operational platforms.",
     None, "Active, Damaged, Destroyed, Withdrawn",
     "hull_integrity_pct, engine_status",
     "Which platforms were destroyed? When did PNS Aslat sink? Which platforms withdrew? How many platforms were still active at the end of the game? When was PNS Khaibar withdrawn?"),

    ("platform_telemetry_log", "current_zone",
     "Name of the game zone this platform is currently located in, determined by checking if the platform's lat/lng falls within any defined zone boundary. Empty string if the platform is outside all defined zones. Used for tracking zone occupancy and correlating actions with geographic areas.",
     None, "Zone Alpha, Zone Bravo, Zone Charlie, Zone Delta, Zone Echo, Zone Foxtrot, Zone Golf, Zone Hotel",
     "latitude, longitude, zone_boundaries.zone_name",
     "Which platforms were in Zone Alpha at tick 1000? How long did INS Vikramaditya spend in Zone Foxtrot? When did Red force enter Zone Alpha?"),

    ("platform_telemetry_log", "visibility_km",
     "Environmental visibility at the platform's location in kilometres. Base visibility is 20km but drops to 12km every 500 ticks for 100 ticks (simulating fog banks). Gaussian noise added for realism. Low visibility affects radar detection confidence and tactical decisions.",
     "km", "2-25",
     "sea_state, weather_condition",
     "What was visibility during the engagement? When was visibility lowest? Did fog affect the battle? What was average visibility during combat ticks 1500-3000?"),

    ("platform_telemetry_log", "sea_state",
     "Sea roughness on an integer scale from 1 (calm/glassy) to 9 (phenomenal/extreme). Varies sinusoidally over time with random noise. Higher sea states affect ship speed, crew comfort, helicopter operations, and small boat launches. Follows the Douglas sea scale.",
     "Douglas scale 1-9", "1-6",
     "visibility_km",
     "What was the sea state during the battle? Was the sea rough at tick 2000? What was the average sea state?"),

    ("platform_telemetry_log", "alert_flag",
     "Boolean flag that is True when a critical condition exists at this tick. Alerts are triggered by: hull integrity below 50% (critical damage), fuel below 15% of capacity (low fuel), or engine status 'Damaged' (engine malfunction). Used to quickly find all critical events.",
     None, "true, false",
     "alert_description, hull_integrity_pct, fuel_level, engine_status",
     "Were there any alerts during the game? How many alert events occurred? When did the first alert trigger for Blue force?"),

    ("platform_telemetry_log", "alert_description",
     "Text description explaining what triggered the alert flag, if any. Possible values: 'Critical hull damage' (hull < 50%), 'Low fuel warning' (fuel < 15% capacity), 'Engine malfunction' (engine damaged). Empty string when no alert is active.",
     None, "Critical hull damage, Low fuel warning, Engine malfunction",
     "alert_flag",
     "What types of alerts were raised? Which platforms had critical hull damage alerts? How many low fuel warnings were issued?"),

    # ==============================================================
    # TABLE 5: tactical_actions
    # Discrete tactical events performed by platforms
    # ==============================================================
    ("tactical_actions", "action_id",
     "Unique auto-incrementing identifier for each tactical action. Primary key.",
     None, "1+",
     None,
     None),

    ("tactical_actions", "game_id",
     "Foreign key linking this action to the game session.",
     None, "1+",
     "game.game_id",
     None),

    ("tactical_actions", "platform_id",
     "Foreign key identifying which platform performed this action. Join with platform_profile for the platform name and type.",
     None, "1-24",
     "platform_profile.platform_id, platform_profile.platform_name",
     "What actions did INS Kolkata perform? How many tactical actions did Blue force platforms take?"),

    ("tactical_actions", "force_id",
     "Foreign key identifying the force of the platform that performed this action.",
     None, "1-4",
     "force.force_id",
     "How many actions did Red force take? Compare tactical activity between Blue and Red."),

    ("tactical_actions", "clock_tick",
     "Game clock tick when this action was performed. Use this to correlate actions with telemetry data and other events at the same tick.",
     "ticks", "0-5000",
     "real_timestamp, platform_telemetry_log.clock_tick",
     "What actions happened at tick 1500? What actions occurred during the battle phase? Show me all actions between tick 2000 and 3000."),

    ("tactical_actions", "real_timestamp",
     "Real-world timestamp when this action was performed. Corresponds to the clock_tick.. Use this column for natural language time queries like yesterday, today, 1:00 PM, AM, PM, hours, minutes, and dates.",
     None, None,
     "clock_tick",
     "What actions happened at noon? Show actions during the first hour."),

    ("tactical_actions", "action_type",
     "Type of tactical action from a standardised list. Categories include: sensor actions (RADAR_ON, RADAR_OFF, SONAR_ACTIVATED, SONAR_DEACTIVATED, AIR_SEARCH_INITIATED), weapon actions (MISSILE_FIRED, TORPEDO_LAUNCHED, DEPTH_CHARGE_DEPLOYED, WEAPON_SYSTEM_ARMED, COUNTERMEASURE_DEPLOYED), movement actions (COURSE_CHANGE, SPEED_CHANGE, EVASIVE_MANOEUVRE, DIVE, SURFACE), zone actions (ZONE_ENTRY, ZONE_EXIT), status actions (DAMAGE_REPORTED, REPAIR_INITIATED, REPAIR_COMPLETED, PLATFORM_DESTROYED, COMMUNICATION_BLACKOUT). This is the most important field for filtering tactical activity.",
     None, "RADAR_ON, RADAR_OFF, MISSILE_FIRED, TORPEDO_LAUNCHED, COURSE_CHANGE, SPEED_CHANGE, DIVE, SURFACE, ZONE_ENTRY, ZONE_EXIT, DAMAGE_REPORTED, PLATFORM_DESTROYED, EVASIVE_MANOEUVRE, COUNTERMEASURE_DEPLOYED, WEAPON_SYSTEM_ARMED, AIR_SEARCH_INITIATED, COMMUNICATION_BLACKOUT, REPAIR_COMPLETED",
     "platform_id, target_platform_id, outcome",
     "How many missiles were fired? When did Blue force activate radar? How many course changes did PNS Babur make? Which platforms performed evasive manoeuvres? How many ZONE_ENTRY actions happened for Zone Alpha?"),

    ("tactical_actions", "target_platform_id",
     "Foreign key referencing the target platform of this action, if applicable. Set for actions like MISSILE_FIRED and TORPEDO_LAUNCHED where there is a specific target. NULL/empty for actions without a target like RADAR_ON or COURSE_CHANGE.",
     None, "1-24 or NULL",
     "platform_profile.platform_id, action_type",
     "Which platforms were targeted by missiles? Who was the target of torpedo launches? How many times was PNS Aslat targeted?"),

    ("tactical_actions", "outcome",
     "Result of the action. 'success' means the action was completed successfully. 'failed' means it did not achieve its goal (e.g. missile missed). 'partial' means partially effective. Most non-combat actions are 'success'. Combat outcomes vary.",
     None, "success, failed, partial",
     "action_type",
     "How many missiles hit their target? What was the success rate of torpedo launches? How many failed actions were there?"),

    ("tactical_actions", "zone_id",
     "Foreign key referencing which zone this action occurred in, if the platform was inside a defined zone at the time. NULL if the platform was outside all zones. Join with zone_boundaries for zone details.",
     None, "1-8 or NULL",
     "zone_boundaries.zone_id, zone_boundaries.zone_name",
     "What actions happened in Zone Alpha? How many combat actions occurred in Zone Foxtrot?"),

    ("tactical_actions", "notes",
     "Free text field with additional details about the action. For scripted events, describes the event type. For radar changes, describes the new status. For combat, may describe attacker and target names.",
     None, None,
     None,
     "Show notes for all combat actions. What happened during scripted events?"),

    # ==============================================================
    # TABLE 6: messages
    # Inter-platform communications
    # ==============================================================
    ("messages", "message_id",
     "Unique auto-incrementing identifier for each message. Primary key. Referenced by main_consolidated_log.message_id to link messages to telemetry ticks.",
     None, "1+",
     "main_consolidated_log.message_id",
     None),

    ("messages", "game_id",
     "Foreign key linking this message to the game session.",
     None, "1+",
     "game.game_id",
     None),

    ("messages", "sender_platform_id",
     "Foreign key identifying the platform that sent this message. Join with platform_profile to get the sender's name and type.",
     None, "1-24",
     "platform_profile.platform_id, platform_profile.platform_name",
     "What messages did INS Vikramaditya send? How many messages did Blue Hawk-1 transmit? Which platform sent the most messages?"),

    ("messages", "receiver_platform_id",
     "Foreign key identifying the intended recipient platform. NULL or empty if the message is a broadcast to multiple platforms. When set, the message is a direct point-to-point communication.",
     None, "1-24 or NULL",
     "platform_profile.platform_id, is_broadcast",
     "Who received messages from INS Kolkata? How many direct messages were sent vs broadcasts?"),

    ("messages", "clock_tick",
     "Game clock tick when this message was sent. Use to correlate messages with events happening at the same time in telemetry and tactical actions.",
     "ticks", "0-5000",
     "real_timestamp",
     "What messages were sent at tick 1500? Show all communications during the battle. How many messages were sent in the first 1000 ticks?. Use this column for natural language time queries like yesterday, today, 1:00 PM, AM, PM, hours, minutes, and dates."),

    ("messages", "real_timestamp",
     "Real-world timestamp when this message was sent.. Use this column for natural language time queries like yesterday, today, 1:00 PM, AM, PM, hours, minutes, and dates.",
     None, None,
     "clock_tick",
     "What messages were sent at noon?"),

    ("messages", "message_content",
     "The full plain text content of the message. Contains realistic naval communications including position reports, contact reports, weapons orders, distress calls, and coordination messages. Search this field to find messages about specific topics like fuel, contacts, or damage.",
     None, None,
     "message_type",
     "What messages mentioned fuel? Show all distress messages. What communications mentioned PNS Aslat? Were there any messages about radar contacts? What was said during the battle?"),

    ("messages", "message_type",
     "Classification of the message: 'informational' for routine status reports and position updates. 'tactical' for contact reports, target information, and combat coordination. 'distress' for MAYDAY and emergency messages from damaged platforms. 'command' for orders from senior platforms to subordinates.",
     None, "tactical, informational, distress, command",
     "message_content",
     "How many distress messages were sent? Show all tactical messages during combat. What commands were issued by Blue force? How many informational reports were filed?"),

    ("messages", "is_broadcast",
     "Boolean flag indicating whether this message was sent to multiple recipients (True) or to a single specific platform (False). Broadcasts are sent to an entire force or all forces.",
     None, "true, false",
     "broadcast_scope, receiver_platform_id",
     "How many messages were broadcasts? What percentage of messages were direct vs broadcast?"),

    ("messages", "broadcast_scope",
     "If the message is a broadcast, this specifies who receives it. 'OWN_FORCE' means only platforms in the same force hear it. 'ALL_FORCES' means every platform in the game receives it (used for distress signals). NULL or empty for direct messages.",
     None, "OWN_FORCE, ALL_FORCES",
     "is_broadcast",
     "How many messages were broadcast to all forces? Were distress signals received by everyone?"),

    # ==============================================================
    # TABLE 7: detection_log
    # One row per detection event between platforms
    # ==============================================================
    ("detection_log", "detection_id",
     "Unique auto-incrementing identifier for each detection event. Primary key. A detection event represents one continuous period where one platform was tracking another.",
     None, "1+",
     None,
     None),

    ("detection_log", "game_id",
     "Foreign key linking this detection to the game session.",
     None, "1+",
     "game.game_id",
     None),

    ("detection_log", "clock_tick",
     "Game clock tick when this detection was first established. The moment the detecting platform's sensors first acquired the target.",
     "ticks", "0-5000",
     "real_timestamp, detection_lost_tick",
     "When was the first detection? What detections occurred at tick 1500? How many detections happened during combat?"),

    ("detection_log", "real_timestamp",
     "Real-world timestamp when this detection was first established.. Use this column for natural language time queries like yesterday, today, 1:00 PM, AM, PM, hours, minutes, and dates.",
     None, None,
     "clock_tick",
     "What time was the first detection?"),

    ("detection_log", "detecting_platform_id",
     "Foreign key identifying the platform that made the detection. This is the sensor platform -- the one whose radar or sonar picked up the target. Join with platform_profile for name.",
     None, "1-24",
     "platform_profile.platform_id, detecting_force_id",
     "Which platforms made detections? How many detections did INS Vikramaditya make? Which Blue force platforms detected Red submarines?"),

    ("detection_log", "detecting_force_id",
     "Force ID of the detecting platform. Used to quickly filter detections by team without joining to platform_profile.",
     None, "1-4",
     "force.force_id, detecting_platform_id",
     "How many detections did Blue force make? Which force detected the most targets?"),

    ("detection_log", "detected_platform_id",
     "Foreign key identifying the platform that was detected. This is the target -- the platform whose presence was revealed by the detector's sensors.",
     None, "1-24",
     "platform_profile.platform_id, detected_force_id",
     "Which Red platforms were detected? How many times was PNS Ghazi detected? Was INS Kalvari ever detected by Red force?"),

    ("detection_log", "detected_force_id",
     "Force ID of the detected platform. A platform can only detect platforms from OTHER forces (not its own). Used to analyse which force was most detected.",
     None, "1-4",
     "force.force_id, detected_platform_id",
     "How many Red force platforms were detected by Blue? Which force was detected the most?"),

    ("detection_log", "detection_range_km",
     "Distance in kilometres between the detecting and detected platforms at the moment of initial detection. Shorter ranges generally produce higher confidence detections. Compare with the detector's max radar/sonar range to understand detection quality.",
     "km", "5-450",
     "detection_confidence, platform_profile.radar_range_km",
     "At what range was PNS Babur first detected? What was the average detection range? Were any detections made at extreme range?"),

    ("detection_log", "detected_latitude",
     "Latitude of the detected platform at the moment of detection. Shows where the target was when first spotted.",
     "degrees", "11-24",
     "detected_longitude",
     "Where was PNS Babur when it was detected? Plot all detection locations on a map."),

    ("detection_log", "detected_longitude",
     "Longitude of the detected platform at the moment of detection.",
     "degrees", "43-70",
     "detected_latitude",
     "Show detection locations for all Red force platforms."),

    ("detection_log", "detection_confidence",
     "Confidence level of the detection based on range relative to max sensor range. 'Confirmed' when target is within 30% of max range (very clear signal). 'Probable' when between 30-60% of max range. 'Possible' when beyond 60% of max range (weak or ambiguous signal).",
     None, "Confirmed, Probable, Possible",
     "detection_range_km, platform_profile.radar_range_km",
     "How many confirmed detections were there? What percentage of detections were only 'Possible'? How confident were Blue's detections of Red submarines?"),

    ("detection_log", "detection_method",
     "The sensor that made the detection. 'Radar' for electromagnetic detection (works on surface targets only, requires radar_status = On). 'Sonar' for acoustic detection (works underwater, used by submarines and ships with sonar). 'Visual' for line-of-sight sighting (rare).",
     None, "Radar, Sonar, Visual",
     "platform_telemetry_log.radar_status, platform_telemetry_log.sonar_status",
     "Were Red submarines detected by radar or sonar? How many sonar detections were made? What percentage of detections were radar vs sonar?"),

    ("detection_log", "detection_lost_tick",
     "Game clock tick when this detection was lost -- meaning the target moved out of sensor range, the sensor was turned off, or the target submerged below radar depth. NULL if the detection was still active at game end (tick 5000).",
     "ticks", "0-5000 or NULL",
     "clock_tick, detection_duration_ticks",
     "When did Blue lose track of PNS Ghazi? How many detections were lost during the battle?"),

    ("detection_log", "detection_lost_timestamp",
     "Real-world timestamp when this detection was lost. NULL if still active at game end.",
     None, None,
     "detection_lost_tick",
     "What time did we lose contact with the submarine?"),

    ("detection_log", "detection_duration_ticks",
     "How many clock ticks the detection was continuously maintained. Calculated as detection_lost_tick - clock_tick. Longer durations mean more stable tracking. Short durations suggest the target was at the edge of sensor range or the sensor was cycling.",
     "ticks", "1-5000",
     "clock_tick, detection_lost_tick",
     "How long was PNS Babur tracked by Blue? What was the average detection duration? Which detection lasted the longest?"),

    # ==============================================================
    # TABLE 8: zone_boundaries
    # Geographic zones defined in the game
    # ==============================================================
    ("zone_boundaries", "zone_id",
     "Unique integer identifier for each zone. Primary key. Referenced by tactical_actions.zone_id.",
     None, "1-8",
     "tactical_actions.zone_id",
     "How many zones are defined?"),

    ("zone_boundaries", "game_id",
     "Foreign key linking this zone to the game session.",
     None, "1+",
     "game.game_id",
     None),

    ("zone_boundaries", "zone_name",
     "Human-readable name of the zone using NATO phonetic alphabet: Zone Alpha (Central Arabian Sea), Zone Bravo (Western Approaches), Zone Charlie (Eastern Sector), Zone Delta (Shipping Lanes), Zone Echo (Gulf of Oman), Zone Foxtrot (Objective Area), Zone Golf (Horn of Africa), Zone Hotel (Gulf of Aden).",
     None, "Zone Alpha, Zone Bravo, Zone Charlie, Zone Delta, Zone Echo, Zone Foxtrot, Zone Golf, Zone Hotel",
     "platform_telemetry_log.current_zone",
     "What zones are defined? Which zone is the objective area? Where is Zone Alpha?"),

    ("zone_boundaries", "boundary_coordinates",
     "JSON array of latitude/longitude coordinate pairs defining the polygon boundary of this zone. Each element has 'lat' and 'lng' fields. Used for map visualization and for determining if a platform is inside the zone.",
     None, None,
     "zone_name",
     "What are the boundaries of Zone Alpha? Show zone boundaries on a map."),

    ("zone_boundaries", "zone_type",
     "Classification of the zone's purpose. 'patrol' means forces conduct regular patrols here. 'exclusion' means platforms should avoid this area. 'objective' means this is a key tactical objective. 'neutral' means it is a non-contested area.",
     None, "patrol, exclusion, objective, neutral",
     "zone_name",
     "Which zones are exclusion zones? What is the objective zone? Which zones are neutral?"),

    ("zone_boundaries", "description",
     "Free text description of what this zone represents and its significance in the wargame scenario.",
     None, None,
     "zone_name, zone_type",
     "Describe Zone Foxtrot. What is the purpose of the exclusion zone?"),

    # ==============================================================
    # TABLE 9: main_consolidated_log
    # Denormalized view with names copied in. Primary query target.
    # ==============================================================
    ("main_consolidated_log", "consolidated_id",
     "Unique auto-incrementing row identifier. Primary key. One row per platform per tick, same count as platform_telemetry_log.",
     None, "1-120024",
     None,
     None),

    ("main_consolidated_log", "game_id",
     "Foreign key to game table.",
     None, "1+",
     "game.game_id",
     None),

    ("main_consolidated_log", "clock_tick",
     "Game clock tick for this record. Same as platform_telemetry_log.clock_tick. Use this as the primary time axis.",
     "ticks", "0-5000",
     "real_timestamp",
     "Show all activity at tick 1000. What happened between tick 1500 and 2000?. Use this column for natural language time queries like yesterday, today, 1:00 PM, AM, PM, hours, minutes, and dates."),

    ("main_consolidated_log", "real_timestamp",
     "Real-world timestamp for this record.. Use this column for natural language time queries like yesterday, today, 1:00 PM, AM, PM, hours, minutes, and dates.",
     None, None,
     "clock_tick",
     "What happened at noon?"),

    ("main_consolidated_log", "force_id",
     "Foreign key to force table. Identifies the team.",
     None, "1-4",
     "force_name",
     "Show Blue force activity."),

    ("main_consolidated_log", "force_name",
     "Name of the force copied from the force table for easy querying. Avoids the need for JOIN when filtering by force name. Values: Blue, Red, Green, Yellow.",
     None, "Blue, Red, Green, Yellow",
     "force_id",
     "Show all Blue force data. Compare Red vs Blue fuel consumption. What was Green force doing at tick 2000?"),

    ("main_consolidated_log", "platform_id",
     "Foreign key identifying the platform.",
     None, "1-24",
     "platform_name",
     "Show data for platform 1."),

    ("main_consolidated_log", "platform_name",
     "Name of the platform copied from platform_profile for easy querying. Avoids JOINs. Contains full vessel names like 'INS Vikramaditya', 'PNS Babur', 'Blue Hawk-1'.",
     None, None,
     "platform_id",
     "Show all data for INS Vikramaditya. Track PNS Babur throughout the game. What was Blue Hawk-1 doing at tick 3000?"),

    ("main_consolidated_log", "platform_type",
     "Platform type copied from platform_profile. 'ship', 'aircraft', or 'submarine'. Use for filtering and comparing behaviour across platform types.",
     None, "ship, aircraft, submarine",
     None,
     "Compare fuel usage across all aircraft. Show all submarine activity. How do ships and submarines compare in speed?"),

    ("main_consolidated_log", "latitude",
     "Platform latitude at this tick. Same as telemetry. Use for mapping.",
     "degrees", "11-24",
     "longitude",
     "Where was INS Vikramaditya at tick 2000? Plot Blue force positions."),

    ("main_consolidated_log", "longitude",
     "Platform longitude at this tick. Same as telemetry.",
     "degrees", "43-70",
     "latitude",
     "Show positions of all platforms at tick 1500."),

    ("main_consolidated_log", "speed_knots",
     "Platform speed at this tick. Same as telemetry.",
     "knots", "0-480",
     "fuel_consumed_interval",
     "What was the average speed of all Blue force ships?"),

    ("main_consolidated_log", "course_deg",
     "Direction of travel at this tick. Same as telemetry.",
     "degrees", "0-360",
     None,
     "What direction was PNS Babur heading?"),

    ("main_consolidated_log", "altitude_meters",
     "Aircraft altitude at this tick. 0 for ships and submarines.",
     "meters", "0-8000",
     "platform_type",
     "What altitude were aircraft flying at?"),

    ("main_consolidated_log", "depth_meters",
     "Submarine depth at this tick. 0 for ships and aircraft.",
     "meters", "0-250",
     "platform_type",
     "How deep were submarines operating?"),

    ("main_consolidated_log", "fuel_level",
     "Fuel remaining at this tick in litres.",
     "litres", "0-8000",
     "fuel_consumed_interval",
     "How much fuel does INS Vikramaditya have left?"),

    ("main_consolidated_log", "fuel_consumed_interval",
     "Fuel burned since last tick. Sum for total consumption.",
     "litres", "0.1-5.0",
     "fuel_level, speed_knots",
     "What was total fuel consumed by Blue force? How much fuel per km?"),

    ("main_consolidated_log", "radar_status",
     "Radar status at this tick: On, Off, Standby.",
     None, "On, Off, Standby",
     None,
     "Was radar on when the detection happened?"),

    ("main_consolidated_log", "sonar_status",
     "Sonar status at this tick: On, Off.",
     None, "On, Off, Standby",
     None,
     "Was sonar active on the submarine?"),

    ("main_consolidated_log", "hull_integrity_pct",
     "Hull health 0-100%. Tracks battle damage.",
     "percent", "0-100",
     "operational_status",
     "Show hull damage timeline for PNS Aslat."),

    ("main_consolidated_log", "current_zone",
     "Zone the platform is currently in. Empty if outside all zones.",
     None, "Zone Alpha through Zone Hotel",
     None,
     "Which platforms were in Zone Foxtrot during combat?"),

    ("main_consolidated_log", "visibility_km",
     "Environmental visibility at this location.",
     "km", "2-25",
     "sea_state",
     "What was visibility during the battle?"),

    ("main_consolidated_log", "sea_state",
     "Sea roughness 1-9 at this tick.",
     "Douglas scale 1-9", "1-6",
     "visibility_km",
     "What was the sea state at tick 2000?"),

    ("main_consolidated_log", "operational_status",
     "Overall platform status: Active, Damaged, Destroyed, Withdrawn.",
     None, "Active, Damaged, Destroyed, Withdrawn",
     "hull_integrity_pct",
     "Which platforms were active at the end of the game?"),

    ("main_consolidated_log", "message_sent",
     "Boolean: True if this platform sent a message at this exact clock tick. False otherwise. Use to find ticks where communication occurred.",
     None, "true, false",
     "message_type, message_id",
     "When did INS Vikramaditya send messages? How many ticks had messages sent?"),

    ("main_consolidated_log", "message_type",
     "Type of message sent at this tick, if any: tactical, informational, distress, command. Empty if no message was sent (message_sent = false).",
     None, "tactical, informational, distress, command",
     "message_sent, message_id",
     "When were distress messages sent? What types of messages were sent during combat?"),

    ("main_consolidated_log", "message_id",
     "Foreign key referencing the messages table. If a message was sent at this tick by this platform, this links to the full message record where you can read the message_content. NULL if no message was sent.",
     None, None,
     "message_sent, messages.message_id, messages.message_content",
     "What was the content of the message sent by INS Kolkata at tick 1500? Show full messages from Blue force."),

    # ==============================================================
    # TABLE 10: schema_metadata
    # Self-referential table describing all columns (this table!)
    # ==============================================================
    ("schema_metadata", "metadata_id",
     "Unique auto-incrementing row identifier for each metadata entry. Primary key.",
     None, "1+",
     None,
     None),

    ("schema_metadata", "table_name",
     "Name of the database table this metadata row describes. One of the 11 tables in the schema.",
     None, "game, force, platform_profile, platform_telemetry_log, tactical_actions, messages, detection_log, zone_boundaries, main_consolidated_log, schema_metadata, query_log",
     "column_name",
     "Which tables are in the database? Describe the schema."),

    ("schema_metadata", "column_name",
     "Name of the specific column within the table that this metadata row describes.",
     None, None,
     "table_name",
     "What columns does the platform_telemetry_log table have?"),

    ("schema_metadata", "description",
     "Detailed natural language description of what this column contains, its purpose, how it relates to the wargame, and how to interpret its values. This is the main text the RAG system searches against.",
     None, None,
     None,
     "What column stores fuel data? Which column tracks ship position?"),

    ("schema_metadata", "unit",
     "Unit of measurement for this column, if applicable. Examples: litres, knots, degrees, km, percent, ticks, personnel.",
     None, None,
     None,
     "What units is fuel measured in? Is speed in knots or km/h?"),

    ("schema_metadata", "typical_range",
     "Expected range of values for this column. Helps the LLM understand what values to expect in WHERE clauses and comparisons.",
     None, None,
     None,
     "What is the normal range for hull integrity? What speed range do ships operate at?"),

    ("schema_metadata", "related_columns",
     "Comma-separated list of columns commonly queried together with this one. Helps the LLM construct efficient JOINs and multi-column queries.",
     None, None,
     None,
     None),

    ("schema_metadata", "example_questions",
     "Sample natural language questions that would require this column to answer. Used during RAG retrieval to match user questions to relevant columns.",
     None, None,
     None,
     None),

    ("schema_metadata", "embedding",
     "Vector embedding of the description field, generated by the embedding model (e.g. all-MiniLM-L6-v2). Will be VECTOR(384) when pgvector is installed. Used for similarity search in the RAG pipeline.",
     None, None,
     "description",
     None),

    # ==============================================================
    # TABLE 11: query_log
    # Audit trail of all LLM queries
    # ==============================================================
    ("query_log", "query_id",
     "Unique auto-incrementing identifier for each query. Primary key.",
     None, "1+",
     None,
     None),

    ("query_log", "game_id",
     "Foreign key identifying which game session was being queried.",
     None, "1+",
     "game.game_id",
     "How many queries were made about game 1?"),

    ("query_log", "timestamp",
     "Real-world timestamp when the user submitted the query. Used for audit trails and performance tracking.",
     None, None,
     None,
     "When was the last query made? How many queries were made today?"),

    ("query_log", "user_question",
     "The original natural language question typed by the user. Stored exactly as entered for audit and retraining purposes.",
     None, None,
     "generated_sql, final_answer",
     "What questions have been asked? Show all queries about fuel. What was the most recent question?"),

    ("query_log", "generated_sql",
     "The SQL query that the LLM generated from the user's natural language question. Stored for debugging, auditing, and improving the text-to-SQL model.",
     None, None,
     "user_question, sql_executed",
     "Show the SQL generated for the last query. What SQL was produced for fuel questions?"),

    ("query_log", "sql_executed",
     "Boolean indicating whether the generated SQL was successfully executed against PostgreSQL. False if the SQL had syntax errors or referenced non-existent tables/columns.",
     None, "true, false",
     "generated_sql, execution_time_ms",
     "How many queries failed? What was the success rate of SQL generation?"),

    ("query_log", "execution_time_ms",
     "How long the SQL query took to execute in milliseconds. Used for performance monitoring. Long execution times may indicate missing indexes or inefficient queries.",
     "milliseconds", "1-30000",
     "generated_sql, sql_executed",
     "What was the average query execution time? Which query took the longest?"),

    ("query_log", "final_answer",
     "The natural language answer returned to the user by the answer synthesis LLM. Combines the raw SQL results with explanation.",
     None, None,
     "user_question, generated_sql",
     "What answer was given for the fuel question? Show the last answer."),

    ("query_log", "output_type",
     "The format in which the answer was presented to the user. 'text' for plain language answers, 'table' for tabular data, 'chart' for visualisations like bar/line charts, 'map' for geographic plots, 'timeline' for chronological event views.",
     None, "text, table, chart, map, timeline",
     "final_answer",
     "How many map outputs were generated? What output types have been used?"),

    ("query_log", "force_id",
     "Foreign key indicating which force was the subject of the query, if the question was about a specific force. NULL for questions about the overall game.",
     None, "1-4 or NULL",
     "force.force_id",
     "How many questions were asked about Blue force? Which force was queried the most?"),
]


def main():
    print("=" * 60)
    print("Schema Metadata Population Script")
    print("=" * 60)
    print(f"\nTotal metadata entries to insert: {len(METADATA)}")

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Clear existing metadata
        cur.execute("TRUNCATE TABLE schema_metadata RESTART IDENTITY;")
        print("[OK] Cleared existing schema_metadata rows")

        # Insert all metadata
        insert_sql = """
            INSERT INTO schema_metadata
                (table_name, column_name, description, unit, typical_range,
                 related_columns, example_questions, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        for i, (table, col, desc, unit, typical, related, examples) in enumerate(METADATA):
            cur.execute(insert_sql, (
                table, col, desc,
                unit or "", typical or "",
                related or "", examples or "",
                None  # embedding = NULL, filled later by embed_schema.py
            ))

        conn.commit()
        print(f"[OK] Inserted {len(METADATA)} metadata rows")

        # Verify
        cur.execute("SELECT count(*) FROM schema_metadata;")
        count = cur.fetchone()[0]
        print(f"\n[VERIFY] schema_metadata now has {count} rows")

        # Show distribution
        cur.execute("""
            SELECT table_name, count(*) as cols
            FROM schema_metadata
            GROUP BY table_name
            ORDER BY table_name;
        """)
        print("\nColumns described per table:")
        for row in cur.fetchall():
            print(f"  {row[0]:30s} {row[1]:>3d} columns")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        cur.close()
        conn.close()
        print("\nDone. Connection closed.")


if __name__ == "__main__":
    main()