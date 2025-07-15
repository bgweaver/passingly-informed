// zip_lookup.js - Enhanced with full team names for better search results
import fetch from 'node-fetch';

// Comprehensive sports market mapping with full team names
const SPORTS_MARKETS = {
  "Atlanta": ["Atlanta Falcons", "Atlanta Hawks", "Atlanta Braves", "Atlanta United FC"],
  "Austin": ["Austin FC"],
  "Baltimore": ["Baltimore Ravens", "Baltimore Orioles"],
  "Boston": ["New England Patriots", "Boston Celtics", "Boston Red Sox", "Boston Bruins"],
  "Buffalo": ["Buffalo Bills", "Buffalo Sabres"],
  "Charlotte": ["Carolina Panthers", "Charlotte Hornets", "Charlotte FC"],
  "Chicago": ["Chicago Bears", "Chicago Bulls", "Chicago Cubs", "Chicago White Sox", "Chicago Blackhawks", "Chicago Fire FC"],
  "Cincinnati": ["Cincinnati Bengals", "Cincinnati Reds", "FC Cincinnati"],
  "Cleveland": ["Cleveland Browns", "Cleveland Cavaliers", "Cleveland Guardians"],
  "Columbus": ["Columbus Blue Jackets", "Columbus Crew"],
  "Dallas": ["Dallas Cowboys", "Dallas Mavericks", "Texas Rangers", "Dallas Stars", "FC Dallas"],
  "Denver": ["Denver Broncos", "Denver Nuggets", "Colorado Rockies", "Colorado Avalanche", "Colorado Rapids"],
  "Detroit": ["Detroit Lions", "Detroit Pistons", "Detroit Tigers", "Detroit Red Wings"],
  "Green Bay": ["Green Bay Packers"],
  "Houston": ["Houston Texans", "Houston Rockets", "Houston Astros", "Houston Dynamo FC"],
  "Indianapolis": ["Indianapolis Colts", "Indiana Pacers", "Indiana Fever"],
  "Jacksonville": ["Jacksonville Jaguars"],
  "Kansas City": ["Kansas City Chiefs", "Kansas City Royals", "Sporting Kansas City"],
  "Las Vegas": ["Las Vegas Raiders", "Vegas Golden Knights", "Las Vegas Aces"],
  "Los Angeles": ["Los Angeles Lakers", "LA Clippers", "Los Angeles Rams", "Los Angeles Chargers", "Los Angeles Dodgers", "Los Angeles Angels", "Los Angeles Kings", "Anaheim Ducks", "LAFC", "LA Galaxy"],
  "Louisville": ["Louisville City FC"],
  "Memphis": ["Memphis Grizzlies"],
  "Miami": ["Miami Dolphins", "Miami Heat", "Miami Marlins", "Florida Panthers", "Inter Miami CF"],
  "Milwaukee": ["Milwaukee Brewers", "Milwaukee Bucks"],
  "Minneapolis": ["Minnesota Vikings", "Minnesota Timberwolves", "Minnesota Twins", "Minnesota Wild", "Minnesota United FC"],
  "Nashville": ["Tennessee Titans", "Nashville Predators", "Nashville SC"],
  "New Orleans": ["New Orleans Saints", "New Orleans Pelicans"],
  "New York": ["New York Giants", "New York Jets", "New York Knicks", "Brooklyn Nets", "New York Yankees", "New York Mets", "New York Rangers", "New York Islanders", "New York City FC", "New York Red Bulls"],
  "Oklahoma City": ["Oklahoma City Thunder"],
  "Orlando": ["Orlando Magic", "Orlando City SC"],
  "Philadelphia": ["Philadelphia Eagles", "Philadelphia 76ers", "Philadelphia Phillies", "Philadelphia Flyers", "Philadelphia Union"],
  "Phoenix": ["Arizona Cardinals", "Phoenix Suns", "Arizona Diamondbacks", "Arizona Coyotes", "Phoenix Rising FC"],
  "Pittsburgh": ["Pittsburgh Steelers", "Pittsburgh Pirates", "Pittsburgh Penguins", "Pittsburgh Riverhounds SC"],
  "Portland": ["Portland Trail Blazers", "Portland Timbers"],
  "Sacramento": ["Sacramento Kings", "Sacramento Republic FC"],
  "Salt Lake City": ["Utah Jazz", "Real Salt Lake"],
  "San Antonio": ["San Antonio Spurs", "San Antonio FC"],
  "San Diego": ["San Diego Padres", "San Diego FC"],
  "San Francisco": ["San Francisco 49ers", "Golden State Warriors", "San Francisco Giants", "San Jose Earthquakes"],
  "San Jose": ["San Jose Sharks", "San Jose Earthquakes"],
  "Seattle": ["Seattle Seahawks", "Seattle Mariners", "Seattle Kraken", "Seattle Sounders FC"],
  "St. Louis": ["St. Louis Blues", "St. Louis City SC"],
  "Tampa": ["Tampa Bay Buccaneers", "Tampa Bay Lightning", "Tampa Bay Rays", "Tampa Bay Rowdies"],
  "Toronto": ["Toronto Raptors", "Toronto Maple Leafs", "Toronto Blue Jays", "Toronto FC"],
  "Washington": ["Washington Commanders", "Washington Capitals", "Washington Nationals", "Washington Wizards", "D.C. United"]
};

// Enhanced regional fallbacks with full team names
const REGIONAL_FALLBACKS = {
  "Alabama": ["Atlanta Falcons", "Atlanta Braves"],
  "Alaska": ["Seattle Seahawks", "Seattle Mariners"],
  "Arizona": ["Arizona Cardinals", "Phoenix Suns", "Arizona Diamondbacks"],
  "Arkansas": ["Kansas City Chiefs", "Kansas City Royals"],
  "Colorado": ["Denver Broncos", "Denver Nuggets", "Colorado Rockies"],
  "Connecticut": ["New England Patriots", "Boston Celtics", "Boston Red Sox"],
  "Delaware": ["Philadelphia Eagles", "Philadelphia 76ers", "Philadelphia Phillies"],
  "Florida": ["Miami Dolphins", "Miami Heat", "Miami Marlins"],
  "Georgia": ["Atlanta Falcons", "Atlanta Hawks", "Atlanta Braves"],
  "Hawaii": ["Golden State Warriors", "San Francisco Giants"],
  "Idaho": ["Seattle Seahawks", "Seattle Mariners"],
  "Illinois": ["Chicago Bears", "Chicago Bulls", "Chicago Cubs"],
  "Indiana": ["Indianapolis Colts", "Indiana Pacers"],
  "Iowa": ["Kansas City Chiefs", "Kansas City Royals"],
  "Kansas": ["Kansas City Chiefs", "Kansas City Royals"],
  "Kentucky": ["Cincinnati Bengals", "Cincinnati Reds"],
  "Louisiana": ["New Orleans Saints", "New Orleans Pelicans"],
  "Maine": ["New England Patriots", "Boston Celtics", "Boston Red Sox"],
  "Maryland": ["Baltimore Ravens", "Baltimore Orioles", "Washington Commanders"],
  "Massachusetts": ["New England Patriots", "Boston Celtics", "Boston Red Sox"],
  "Michigan": ["Detroit Lions", "Detroit Pistons", "Detroit Tigers"],
  "Minnesota": ["Minnesota Vikings", "Minnesota Timberwolves", "Minnesota Twins"],
  "Mississippi": ["New Orleans Saints", "New Orleans Pelicans"],
  "Missouri": ["Kansas City Chiefs", "Kansas City Royals"],
  "Montana": ["Denver Broncos", "Denver Nuggets"],
  "Nebraska": ["Kansas City Chiefs", "Kansas City Royals"],
  "Nevada": ["Las Vegas Raiders", "Vegas Golden Knights"],
  "New Hampshire": ["New England Patriots", "Boston Celtics", "Boston Red Sox"],
  "New Jersey": ["New York Giants", "New York Jets", "New York Knicks"],
  "New Mexico": ["Denver Broncos", "Denver Nuggets"],
  "New York": ["New York Giants", "New York Jets", "New York Knicks"],
  "North Carolina": ["Carolina Panthers", "Charlotte Hornets"],
  "North Dakota": ["Minnesota Vikings", "Minnesota Timberwolves"],
  "Ohio": ["Cleveland Browns", "Cleveland Cavaliers"],
  "Oklahoma": ["Oklahoma City Thunder"],
  "Oregon": ["Portland Trail Blazers", "Portland Timbers"],
  "Pennsylvania": ["Philadelphia Eagles", "Philadelphia 76ers", "Philadelphia Phillies"],
  "Rhode Island": ["New England Patriots", "Boston Celtics", "Boston Red Sox"],
  "South Carolina": ["Carolina Panthers", "Charlotte Hornets"],
  "South Dakota": ["Minnesota Vikings", "Minnesota Timberwolves"],
  "Tennessee": ["Tennessee Titans", "Nashville Predators"],
  "Texas": ["Dallas Cowboys", "Dallas Mavericks", "Texas Rangers"],
  "Utah": ["Utah Jazz"],
  "Vermont": ["New England Patriots", "Boston Celtics", "Boston Red Sox"],
  "Virginia": ["Washington Commanders", "Washington Capitals", "Washington Nationals"],
  "Washington": ["Seattle Seahawks", "Seattle Mariners", "Seattle Kraken"],
  "West Virginia": ["Pittsburgh Steelers", "Pittsburgh Pirates", "Pittsburgh Penguins"],
  "Wisconsin": ["Green Bay Packers", "Milwaukee Brewers", "Milwaukee Bucks"],
  "Wyoming": ["Denver Broncos", "Denver Nuggets"]
};

// Metro area mappings with full team names
const METRO_AREAS = {
  "New York Metro": {
    cities: ["New York", "Newark", "Jersey City", "Yonkers", "Paterson", "Elizabeth", "Edison", "Woodbridge"],
    teams: ["New York Giants", "New York Jets", "New York Knicks", "Brooklyn Nets", "New York Yankees", "New York Mets", "New York Rangers", "New York Islanders"]
  },
  "Los Angeles Metro": {
    cities: ["Los Angeles", "Long Beach", "Anaheim", "Santa Ana", "Irvine", "Huntington Beach", "Glendale", "Santa Clarita"],
    teams: ["Los Angeles Lakers", "LA Clippers", "Los Angeles Rams", "Los Angeles Chargers", "Los Angeles Dodgers", "Los Angeles Angels", "Los Angeles Kings", "Anaheim Ducks"]
  },
  "Chicago Metro": {
    cities: ["Chicago", "Aurora", "Rockford", "Joliet", "Naperville", "Peoria", "Elgin", "Waukegan"],
    teams: ["Chicago Bears", "Chicago Bulls", "Chicago Cubs", "Chicago White Sox", "Chicago Blackhawks"]
  },
  "Dallas Metro": {
    cities: ["Dallas", "Fort Worth", "Arlington", "Plano", "Irving", "Garland", "Frisco", "McKinney"],
    teams: ["Dallas Cowboys", "Dallas Mavericks", "Texas Rangers", "Dallas Stars"]
  },
  "Philadelphia Metro": {
    cities: ["Philadelphia", "Allentown", "Reading", "Camden", "Trenton", "Atlantic City"],
    teams: ["Philadelphia Eagles", "Philadelphia 76ers", "Philadelphia Phillies", "Philadelphia Flyers"]
  },
  "Houston Metro": {
    cities: ["Houston", "Sugar Land", "Baytown", "Conroe", "Galveston", "Beaumont"],
    teams: ["Houston Texans", "Houston Rockets", "Houston Astros"]
  },
  "Washington Metro": {
    cities: ["Washington", "Arlington", "Alexandria", "Rockville", "Bethesda", "Silver Spring"],
    teams: ["Washington Commanders", "Washington Capitals", "Washington Nationals", "Washington Wizards"]
  },
  "Miami Metro": {
    cities: ["Miami", "Fort Lauderdale", "West Palm Beach", "Hollywood", "Coral Springs", "Pompano Beach"],
    teams: ["Miami Dolphins", "Miami Heat", "Miami Marlins", "Florida Panthers"]
  },
  "Atlanta Metro": {
    cities: ["Atlanta", "Columbus", "Augusta", "Savannah", "Athens", "Sandy Springs", "Roswell"],
    teams: ["Atlanta Falcons", "Atlanta Hawks", "Atlanta Braves"]
  },
  "Boston Metro": {
    cities: ["Boston", "Worcester", "Springfield", "Cambridge", "Lowell", "Brockton", "Quincy"],
    teams: ["New England Patriots", "Boston Celtics", "Boston Red Sox", "Boston Bruins"]
  }
};

// College sports markets with full names
const COLLEGE_MARKETS = {
  "Alabama": ["Alabama Crimson Tide", "Auburn Tigers"],
  "Kentucky": ["Kentucky Wildcats", "Louisville Cardinals"],
  "North Carolina": ["Duke Blue Devils", "North Carolina Tar Heels"],
  "Kansas": ["Kansas Jayhawks", "Kansas State Wildcats"],
  "Indiana": ["Indiana Hoosiers", "Purdue Boilermakers"],
  "Michigan": ["Michigan Wolverines", "Michigan State Spartans"],
  "Ohio": ["Ohio State Buckeyes"],
  "Texas": ["Texas Longhorns", "Texas A&M Aggies"],
  "Florida": ["Florida Gators", "Florida State Seminoles"],
  "Georgia": ["Georgia Bulldogs", "Georgia Tech Yellow Jackets"]
};

function findMetroArea(city) {
  for (const [metroName, metroData] of Object.entries(METRO_AREAS)) {
    if (metroData.cities.some(metroCity => 
      city.toLowerCase().includes(metroCity.toLowerCase()) || 
      metroCity.toLowerCase().includes(city.toLowerCase())
    )) {
      return metroData.teams;
    }
  }
  return null;
}

function findCollegeTeams(state) {
  return COLLEGE_MARKETS[state] || [];
}

export async function getTeamsFromZip(zipCode) {
  try {
    console.log(`🔍 Fetching data for ZIP: ${zipCode}`);
    
    const response = await fetch(`http://api.zippopotam.us/us/${zipCode}`);
    
    if (!response.ok) {
      throw new Error(`Invalid ZIP code: ${zipCode} (HTTP ${response.status})`);
    }
    
    const data = await response.json();
    console.log('📦 Raw API response:', JSON.stringify(data, null, 2));
    
    if (!data.places || data.places.length === 0) {
      throw new Error(`No places found for ZIP code: ${zipCode}`);
    }
    
    const place = data.places[0];
    const city = place['place name'];
    const state = place['state'];
    const stateAbbr = place['state abbreviation'];
    
    console.log(`📍 Looking up teams for ${city}, ${state} (${stateAbbr})`);
    
    // Strategy 1: Exact city match
    const directTeams = SPORTS_MARKETS[city];
    if (directTeams && directTeams.length > 0) {
      return {
        city: city,
        state: state,
        teams: directTeams,
        source: 'direct_city_match',
        confidence: 'high'
      };
    }
    
    // Strategy 2: Metro area match
    const metroTeams = findMetroArea(city);
    if (metroTeams && metroTeams.length > 0) {
      return {
        city: city,
        state: state,
        teams: metroTeams,
        source: 'metro_area_match',
        confidence: 'high'
      };
    }
    
    // Strategy 3: Partial city name matching
    const cityMatches = Object.keys(SPORTS_MARKETS).filter(market => {
      if (!city || !market) return false;
      return city.toLowerCase().includes(market.toLowerCase()) || 
             market.toLowerCase().includes(city.toLowerCase());
    });
    
    if (cityMatches.length > 0) {
      return {
        city: city,
        state: state,
        teams: SPORTS_MARKETS[cityMatches[0]],
        source: 'partial_city_match',
        confidence: 'medium'
      };
    }
    
    // Strategy 4: State-level professional teams
    const stateTeams = REGIONAL_FALLBACKS[state];
    if (stateTeams && stateTeams.length > 0) {
      return {
        city: city,
        state: state,
        teams: stateTeams,
        source: 'state_fallback',
        confidence: 'medium'
      };
    }
    
    // Strategy 5: Include college teams for states with strong college sports
    const collegeTeams = findCollegeTeams(state);
    if (collegeTeams.length > 0) {
      return {
        city: city,
        state: state,
        teams: collegeTeams,
        source: 'college_sports',
        confidence: 'low'
      };
    }
    
    // Strategy 6: Geographic proximity fallback
    const proximityTeams = getProximityTeams(state);
    if (proximityTeams.length > 0) {
      return {
        city: city,
        state: state,
        teams: proximityTeams,
        source: 'geographic_proximity',
        confidence: 'low'
      };
    }
    
    // Ultimate fallback
    return {
      city: city,
      state: state,
      teams: ["National sports news"],
      source: 'national_fallback',
      confidence: 'very_low'
    };
    
  } catch (error) {
    console.error('❌ Error looking up ZIP code:', error.message);
    return null;
  }
}

function getProximityTeams(state) {
  // Regional proximity mapping for states without clear allegiances
  const proximityMap = {
    "Maine": ["New England Patriots", "Boston Celtics", "Boston Red Sox"],
    "New Hampshire": ["New England Patriots", "Boston Celtics", "Boston Red Sox"],
    "Vermont": ["New England Patriots", "Boston Celtics", "Boston Red Sox"],
    "Delaware": ["Philadelphia Eagles", "Philadelphia 76ers", "Philadelphia Phillies"],
    "West Virginia": ["Pittsburgh Steelers", "Pittsburgh Pirates", "Pittsburgh Penguins"],
    "Montana": ["Denver Broncos", "Denver Nuggets"],
    "Wyoming": ["Denver Broncos", "Denver Nuggets"],
    "North Dakota": ["Minnesota Vikings", "Minnesota Timberwolves"],
    "South Dakota": ["Minnesota Vikings", "Minnesota Timberwolves"],
    "Alaska": ["Seattle Seahawks", "Seattle Mariners"],
    "Hawaii": ["Golden State Warriors", "San Francisco Giants"]
  };
  
  return proximityMap[state] || [];
}

// Enhanced test function with more comprehensive output
async function testZipLookup() {
  const examples = [
    "46201", // Indianapolis
    "60601", // Chicago
    "10001", // New York
    "90210", // Beverly Hills
    "30309", // Atlanta
    "02101", // Boston
    "75201", // Dallas
    "33101", // Miami
    "98101", // Seattle
    "80202", // Denver
    "37201", // Nashville
    "15201", // Pittsburgh
    "97201", // Portland
    "84101", // Salt Lake City
    "73101"  // Oklahoma City
  ];
  
  console.log('\n🧪 Testing ZIP Code Lookup System');
  console.log('='.repeat(80));
  
  for (const zip of examples) {
    console.log(`\n📍 Testing ZIP: ${zip}`);
    console.log('-'.repeat(40));
    
    const result = await getTeamsFromZip(zip);
    if (result) {
      console.log(`✅ Location: ${result.city}, ${result.state}`);
      console.log(`🏆 Teams: ${result.teams.join(", ")}`);
      console.log(`📊 Source: ${result.source} (${result.confidence} confidence)`);
    } else {
      console.log(`❌ Failed to get data for ${zip}`);
    }
  }
  
  console.log('\n' + '='.repeat(80));
  console.log('🏁 Test completed!');
}

// Export test function for standalone testing
export { testZipLookup };

// Uncomment to run tests:
// testZipLookup();