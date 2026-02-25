import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, MoveRight, Wallet, Search } from "lucide-react";
import { taggingApi } from "../services/api";
import { Skeleton } from "../components/common/Skeleton";

// [emoji, searchKeywords] — keywords are space-separated for fast substring matching
const EMOJI_DATA: [string, string][] = [
  // 💵 Money & Finance
  ["💰", "money bag gold finance rich wealth"],
  ["💵", "dollar money cash bill currency"],
  ["💴", "yen money japan currency"],
  ["💶", "euro money europe currency"],
  ["💷", "pound money uk sterling currency"],
  ["💳", "credit card payment debit bank"],
  ["💸", "spending flying money expense cost"],
  ["🏦", "bank building finance savings"],
  ["📈", "chart up growth stocks invest profit"],
  ["📉", "chart down loss decline stocks"],
  ["💹", "chart yen growth finance market"],
  ["🪙", "coin money token currency"],
  ["🧾", "receipt bill invoice payment"],
  ["💲", "dollar sign money price cost"],
  ["🏧", "atm cash withdraw bank machine"],
  ["🤑", "money face rich greedy finance"],
  // 🍔 Food & Drink
  ["🍔", "burger hamburger food fast meal"],
  ["🍕", "pizza food italian slice"],
  ["🍣", "sushi food japanese fish"],
  ["🥗", "salad food healthy green vegetables"],
  ["🍝", "pasta food italian spaghetti noodles"],
  ["🌮", "taco food mexican"],
  ["🌯", "burrito wrap food mexican"],
  ["🥐", "croissant bakery bread pastry breakfast"],
  ["🍞", "bread food bakery toast"],
  ["🥩", "meat steak food beef"],
  ["🍗", "chicken food poultry drumstick"],
  ["🍖", "meat bone food ribs"],
  ["🥓", "bacon food breakfast meat"],
  ["🍳", "egg fried food breakfast cooking"],
  ["🥚", "egg food breakfast"],
  ["🧀", "cheese food dairy"],
  ["🥪", "sandwich food lunch bread"],
  ["🌭", "hotdog food fast sausage"],
  ["🥙", "pita falafel food wrap"],
  ["🧆", "falafel food middle east"],
  ["🥘", "stew food pot cooking"],
  ["🍜", "noodles ramen soup food asian"],
  ["🍲", "soup stew pot food"],
  ["🍛", "curry food indian rice"],
  ["🍱", "bento box food japanese lunch"],
  ["🥟", "dumpling food asian"],
  ["🍰", "cake dessert sweet birthday"],
  ["🍩", "donut doughnut dessert sweet snack"],
  ["🍪", "cookie biscuit dessert sweet snack"],
  ["🍫", "chocolate candy sweet snack"],
  ["🍬", "candy sweet sugar treat"],
  ["🍭", "lollipop candy sweet"],
  ["🍿", "popcorn snack cinema movies"],
  ["🧁", "cupcake dessert sweet bakery"],
  ["🥧", "pie dessert food bake"],
  ["🍦", "ice cream dessert cold sweet"],
  ["🍨", "sundae ice cream dessert"],
  ["🍧", "shaved ice dessert cold"],
  ["🥤", "drink cup soda juice beverage"],
  ["☕", "coffee drink cafe espresso latte"],
  ["🍵", "tea drink green matcha cup"],
  ["🫖", "teapot tea drink kettle"],
  ["🍷", "wine drink alcohol glass bar"],
  ["🍺", "beer drink alcohol pub bar"],
  ["🍻", "cheers beer drink celebration"],
  ["🥂", "champagne toast celebration drink wine"],
  ["🍸", "cocktail martini drink alcohol bar"],
  ["🍹", "tropical drink cocktail alcohol"],
  ["🧃", "juice box drink beverage kids"],
  ["🥛", "milk drink dairy glass"],
  ["🍽️", "restaurant dining plate food meal"],
  ["🧑‍🍳", "chef cook food kitchen restaurant"],
  ["🫒", "olive food oil mediterranean"],
  ["🥑", "avocado food healthy green"],
  ["🍅", "tomato food vegetable red"],
  ["🥕", "carrot food vegetable orange"],
  ["🌽", "corn food vegetable yellow"],
  ["🥦", "broccoli food vegetable green healthy"],
  ["🧄", "garlic food cooking spice"],
  ["🧅", "onion food cooking vegetable"],
  ["🥔", "potato food vegetable"],
  ["🍠", "sweet potato food vegetable"],
  ["🍎", "apple fruit food red healthy"],
  ["🍊", "orange fruit food citrus"],
  ["🍋", "lemon fruit food citrus yellow"],
  ["🍌", "banana fruit food yellow"],
  ["🍇", "grapes fruit food wine purple"],
  ["🍓", "strawberry fruit food berry red"],
  ["🫐", "blueberry fruit food berry"],
  ["🍑", "peach fruit food"],
  ["🍒", "cherry fruit food red"],
  ["🥝", "kiwi fruit food green"],
  ["🍍", "pineapple fruit food tropical"],
  ["🥭", "mango fruit food tropical"],
  ["🥥", "coconut fruit food tropical"],
  ["🌶️", "pepper chili hot spicy food"],
  // 🏠 Home & Housing
  ["🏠", "home house housing rent mortgage"],
  ["🏡", "house garden home property"],
  ["🏢", "office building work commercial"],
  ["🏗️", "construction building renovation work"],
  ["🔑", "key home lock rent property access password security"],
  ["🛋️", "couch sofa furniture living room"],
  ["🛏️", "bed bedroom furniture sleep"],
  ["🚿", "shower bathroom water hygiene"],
  ["🛁", "bathtub bath bathroom"],
  ["🪞", "mirror bathroom vanity reflection"],
  ["🧹", "broom cleaning housework sweep"],
  ["🧺", "laundry basket cleaning clothes"],
  ["🪴", "plant pot garden home decor"],
  ["💡", "lightbulb electricity idea utility"],
  ["🔌", "plug electricity power utility"],
  ["🛠️", "tools repair fix maintenance home"],
  ["🔧", "wrench tool repair fix plumbing"],
  ["🪛", "screwdriver tool repair fix"],
  ["🧰", "toolbox repair maintenance handyman"],
  ["🪣", "bucket cleaning water household"],
  ["🧴", "lotion bottle hygiene bathroom soap"],
  ["🧽", "sponge cleaning kitchen household"],
  ["🪥", "toothbrush hygiene bathroom dental"],
  ["🚰", "water tap faucet plumbing utility"],
  ["🪑", "chair furniture seat home"],
  ["🚪", "door entrance home entry"],
  ["🪟", "window home glass frame"],
  ["🛒", "shopping cart grocery store supermarket"],
  ["🏘️", "houses neighborhood community homes"],
  ["🧲", "magnet tool household attract science physics"],
  ["🪤", "mousetrap pest control home"],
  ["🧯", "fire extinguisher safety emergency"],
  ["🪜", "ladder tool climb home fix"],
  ["🖼️", "frame picture art decor wall"],
  ["🪵", "wood log fireplace material"],
  ["🧱", "brick building construction material"],
  // 🚗 Transport
  ["🚗", "car vehicle automobile transport drive"],
  ["🚕", "taxi cab ride transport"],
  ["🚌", "bus public transport commute"],
  ["🚇", "metro subway train underground transport"],
  ["🚆", "train rail transport commute travel"],
  ["🚂", "locomotive train steam railway"],
  ["🚃", "railway car train carriage"],
  ["✈️", "airplane flight travel airport plane"],
  ["🛫", "departure flight airplane takeoff travel"],
  ["🛬", "arrival flight airplane landing travel"],
  ["🚢", "ship boat cruise sea transport"],
  ["⛵", "sailboat boat sailing wind"],
  ["🚤", "speedboat boat fast water"],
  ["🛶", "canoe boat paddle kayak water"],
  ["🛵", "scooter motorcycle transport"],
  ["🏍️", "motorcycle motorbike transport speed"],
  ["🚲", "bicycle bike cycling transport"],
  ["🛴", "scooter kick transport"],
  ["🛺", "rickshaw auto transport tuk"],
  ["⛽", "fuel gas petrol station car"],
  ["🅿️", "parking car park"],
  ["🚦", "traffic light signal road"],
  ["🛤️", "railway tracks train"],
  ["🚁", "helicopter flight transport"],
  ["🛞", "tire wheel car rubber"],
  ["🚘", "car oncoming vehicle drive"],
  ["🚙", "suv car vehicle sport"],
  ["🛻", "pickup truck vehicle transport"],
  ["🚚", "delivery truck transport moving"],
  ["🚛", "semi truck transport freight"],
  ["🚐", "minibus van transport"],
  ["🚎", "trolleybus transport electric public"],
  ["🛣️", "highway road motorway freeway"],
  // 🛍️ Shopping & Clothing
  ["🛍️", "shopping bags mall store retail"],
  ["👕", "shirt tshirt clothes clothing fashion"],
  ["👗", "dress clothes clothing fashion women"],
  ["👟", "sneakers shoes running sports footwear"],
  ["👠", "heels shoes fashion women footwear"],
  ["👜", "handbag purse bag fashion accessories"],
  ["🧥", "coat jacket clothes winter warm"],
  ["👔", "tie necktie formal work clothes"],
  ["👒", "hat fashion sun accessories"],
  ["🧢", "cap hat fashion accessories"],
  ["💎", "gem diamond jewelry luxury"],
  ["⌚", "watch time accessories luxury fashion"],
  ["👓", "glasses eyewear optical vision"],
  ["🕶️", "sunglasses fashion accessories cool"],
  ["💄", "lipstick makeup cosmetics beauty"],
  ["👙", "bikini swimsuit beach summer clothes"],
  ["🩱", "swimsuit one piece bathing clothes"],
  ["👘", "kimono japanese clothes traditional"],
  ["🥻", "sari clothes traditional indian"],
  ["🧣", "scarf winter warm clothes accessory"],
  ["🧤", "gloves winter warm hands clothes"],
  ["🧦", "socks clothes feet warm"],
  ["👞", "shoe formal dress leather footwear"],
  ["👡", "sandal shoe summer open footwear"],
  ["🥾", "hiking boot shoe outdoor footwear"],
  ["👑", "crown king queen royal luxury"],
  ["🎀", "ribbon bow gift decoration"],
  ["👝", "clutch purse bag evening"],
  ["🎽", "running shirt sport athletic clothes"],
  ["🩳", "shorts clothes summer casual"],
  ["🩴", "flip flop sandal summer beach"],
  ["💅", "nail polish manicure beauty fashion"],
  // 🏥 Health & Wellness
  ["🏥", "hospital health medical doctor emergency"],
  ["💊", "pill medicine medication pharmacy health"],
  ["💉", "syringe vaccine injection medical"],
  ["🩺", "stethoscope doctor medical checkup"],
  ["🩹", "bandage first aid medical injury"],
  ["🦷", "tooth dental dentist health"],
  ["👁️", "eye vision optical glasses health"],
  ["🧘", "yoga meditation wellness mindfulness"],
  ["🏋️", "gym weights fitness workout exercise"],
  ["🤸", "gymnastics exercise sport fitness"],
  ["💆", "massage spa relax wellness"],
  ["🧖", "spa sauna steam wellness relax"],
  ["❤️", "heart love health red"],
  ["🫀", "heart organ medical health"],
  ["🧠", "brain mind mental health thinking"],
  ["♿", "disability accessibility wheelchair"],
  ["🩻", "xray bones medical scan"],
  ["🩼", "crutch injury support medical"],
  ["🦴", "bone skeleton medical body"],
  ["🫁", "lungs breathing medical organ"],
  ["🩸", "blood drop medical donate"],
  ["🏃", "running exercise cardio fitness jog"],
  ["🚴", "cycling bike exercise sport"],
  ["🏊", "swimming pool exercise sport water"],
  ["🧗", "climbing sport exercise adventure"],
  ["🤾", "handball sport exercise ball"],
  ["🤺", "fencing sport exercise sword"],
  ["🏄", "surfing sport water wave beach"],
  ["⚕️", "medical health caduceus symbol"],
  ["🧬", "dna genetics science biology strand"],
  ["🔬", "microscope science research lab medical"],
  // 🎓 Education & Work
  ["🎓", "graduation education university school degree"],
  ["📚", "books reading education library study"],
  ["📖", "book reading education study open"],
  ["✏️", "pencil writing education draw"],
  ["📝", "memo notes writing study document"],
  ["🖥️", "computer desktop screen work tech monitor"],
  ["💼", "briefcase business work office job"],
  ["🏫", "school education building class"],
  ["📐", "ruler triangle math geometry education"],
  ["🧪", "test tube science lab chemistry"],
  ["📏", "ruler measure straight edge office"],
  ["🎒", "backpack school bag student education"],
  ["📓", "notebook journal writing study"],
  ["🗂️", "file folder organize office document"],
  ["📋", "clipboard list check document"],
  ["🖊️", "pen writing ink office"],
  ["🖋️", "fountain pen writing calligraphy"],
  ["✒️", "nib pen ink writing"],
  ["📎", "paperclip office supply attach"],
  ["🗃️", "card file box office organize"],
  ["📊", "bar chart statistics data analytics"],
  ["📑", "tabs document bookmark page"],
  ["📰", "newspaper news media press read"],
  ["🗞️", "rolled newspaper news media press"],
  ["📒", "ledger notebook yellow pages"],
  ["📕", "book closed red reading"],
  ["📗", "book green reading textbook"],
  ["📘", "book blue reading textbook"],
  ["📙", "book orange reading textbook"],
  ["🧑‍💻", "programmer developer coder tech work"],
  ["🧑‍🏫", "teacher education instructor class"],
  ["🧑‍🔬", "scientist research lab education"],
  ["🧑‍⚕️", "doctor health medical professional"],
  ["🧑‍🔧", "mechanic repair fix tool worker"],
  ["🧑‍🌾", "farmer agriculture garden food"],
  ["🧑‍🎨", "artist creative paint design"],
  ["🧑‍✈️", "pilot aviation fly captain"],
  ["🧑‍🚒", "firefighter rescue emergency safety"],
  ["👷", "construction worker build hard hat"],
  ["👮", "police officer law enforcement cop"],
  // 🎮 Entertainment & Fun
  ["🎮", "gaming controller video games play"],
  ["🎬", "movie cinema film clapper"],
  ["🎭", "theater drama performing arts masks"],
  ["🎤", "microphone karaoke sing music"],
  ["🎧", "headphones music audio listen"],
  ["🎵", "music note song sound"],
  ["🎶", "music notes song melody"],
  ["🎸", "guitar music rock instrument"],
  ["🎹", "piano keyboard music instrument"],
  ["🎺", "trumpet music brass instrument"],
  ["🥁", "drum music instrument beat"],
  ["🎲", "dice game board luck casino"],
  ["🧩", "puzzle game jigsaw piece"],
  ["🎯", "target bullseye goal darts aim"],
  ["🎪", "circus tent carnival fun"],
  ["🎠", "carousel ride amusement park fun"],
  ["🎰", "slot machine casino gambling jackpot"],
  ["🎱", "billiards pool ball game"],
  ["🕹️", "joystick arcade retro game"],
  ["🎷", "saxophone music jazz instrument"],
  ["🪕", "banjo music instrument country"],
  ["🎻", "violin fiddle music instrument classical"],
  ["📻", "radio music audio broadcast"],
  ["🎙️", "studio microphone mic podcast recording audio"],
  ["📀", "dvd disc movie media"],
  ["💿", "cd disc music album"],
  ["🎞️", "film frames movie cinema reel"],
  ["📸", "camera flash photo selfie"],
  ["🎨", "art palette paint creative drawing"],
  ["🖌️", "paintbrush art creative drawing"],
  ["🖍️", "crayon draw art color kids"],
  ["🎳", "bowling sport ball pins game"],
  ["🏆", "trophy winner champion award prize"],
  ["🥇", "gold medal first winner champion"],
  ["🥈", "silver medal second runner up"],
  ["🥉", "bronze medal third place"],
  ["🏅", "medal award sports achievement winner"],
  // ⚽ Sports & Activities
  ["⚽", "soccer football sport ball kick"],
  ["🏀", "basketball sport ball hoop"],
  ["🏈", "football american sport ball"],
  ["⚾", "baseball sport ball bat"],
  ["🥎", "softball sport ball"],
  ["🎾", "tennis sport ball racket"],
  ["🏐", "volleyball sport ball net"],
  ["🏉", "rugby sport ball"],
  ["🏸", "badminton sport shuttlecock racket"],
  ["🏓", "table tennis ping pong sport paddle"],
  ["🥊", "boxing glove sport fight"],
  ["🥋", "martial arts karate judo sport"],
  ["⛳", "golf sport flag hole"],
  ["⛷️", "skiing sport winter snow"],
  ["🏂", "snowboard sport winter snow"],
  ["🛷", "sled sport winter snow toboggan"],
  ["⛸️", "ice skating sport winter"],
  ["🏌️", "golf sport swing club"],
  ["🎿", "ski sport winter snow poles"],
  ["🛹", "skateboard sport ride trick"],
  ["🤿", "diving snorkel sport underwater"],
  ["🏹", "archery bow arrow sport"],
  // 🏖️ Travel & Nature
  ["🌴", "palm tree tropical vacation beach"],
  ["🏖️", "beach vacation sand sun summer"],
  ["⛱️", "umbrella beach sun shade summer"],
  ["🌍", "world globe earth travel map"],
  ["🌎", "world globe americas travel"],
  ["🌏", "world globe asia travel"],
  ["🗺️", "map world travel navigation"],
  ["🏔️", "mountain snow nature hiking"],
  ["⛺", "tent camping outdoor nature"],
  ["🏕️", "camping outdoor tent nature park"],
  ["🌅", "sunrise sunset morning nature"],
  ["🌊", "wave ocean sea water surf"],
  ["🏝️", "island tropical vacation beach"],
  ["🗼", "tower landmark tourism sightseeing"],
  ["🗽", "statue liberty usa new york landmark"],
  ["🎢", "roller coaster amusement park fun ride"],
  ["🏰", "castle kingdom fairy tale landmark"],
  ["⛩️", "shrine temple japan torii gate"],
  ["🕌", "mosque religion islam prayer"],
  ["⛪", "church religion christian prayer"],
  ["🕍", "synagogue religion jewish prayer temple"],
  ["🛕", "hindu temple religion prayer"],
  ["🕋", "kaaba mecca islam holy"],
  ["🌋", "volcano nature mountain hot lava"],
  ["🏜️", "desert sand dry hot nature"],
  ["🌲", "evergreen tree forest nature pine"],
  ["🌳", "tree nature deciduous forest"],
  ["🌸", "cherry blossom flower spring japan"],
  ["🌺", "hibiscus flower tropical"],
  ["🌻", "sunflower flower yellow nature"],
  ["🌹", "rose flower red love romantic"],
  ["🌷", "tulip flower spring garden"],
  ["💐", "bouquet flowers gift arrangement"],
  ["🌿", "herb leaf green plant nature"],
  ["🍀", "four leaf clover luck irish"],
  ["🍁", "maple leaf fall autumn canada"],
  ["🍂", "fallen leaf autumn nature"],
  ["🌾", "rice ear grain crop farm"],
  ["🏞️", "national park nature landscape valley"],
  ["🌌", "milky way galaxy night sky stars"],
  ["🌈", "rainbow nature weather colors"],
  ["🌧️", "rain cloud weather water"],
  ["⛈️", "thunder storm lightning weather"],
  ["🌪️", "tornado storm wind weather"],
  ["🌤️", "partly cloudy sun weather"],
  ["🌙", "moon crescent night"],
  ["🌕", "full moon night sky"],
  // 🐕 Pets & Animals
  ["🐕", "dog pet puppy animal canine"],
  ["🐱", "cat pet kitten animal feline"],
  ["🐟", "fish pet aquarium animal sea"],
  ["🐠", "tropical fish pet aquarium colorful"],
  ["🐡", "blowfish puffer fish sea animal"],
  ["🐦", "bird pet animal flying sing"],
  ["🦜", "parrot bird pet colorful talking"],
  ["🦅", "eagle bird animal predator"],
  ["🐹", "hamster pet small animal cute"],
  ["🐰", "rabbit bunny pet animal cute"],
  ["🐢", "turtle pet animal slow reptile"],
  ["🐾", "paw print animal pet foot"],
  ["🦮", "guide dog service pet animal"],
  ["🐈", "cat pet animal feline kitty"],
  ["🐎", "horse animal ride equestrian"],
  ["🦊", "fox animal wild clever"],
  ["🐻", "bear animal wild nature"],
  ["🐼", "panda bear animal cute china"],
  ["🦁", "lion animal wild king jungle"],
  ["🐯", "tiger animal wild stripes"],
  ["🐮", "cow animal farm dairy milk"],
  ["🐷", "pig animal farm pink"],
  ["🐑", "sheep animal farm wool lamb"],
  ["🐔", "chicken animal farm hen"],
  ["🦆", "duck animal bird water"],
  ["🦢", "swan bird animal elegant white"],
  ["🐍", "snake reptile animal slither"],
  ["🦎", "lizard reptile animal gecko"],
  ["🐊", "crocodile alligator animal reptile"],
  ["🐘", "elephant animal large trunk"],
  ["🦒", "giraffe animal tall spots"],
  ["🐪", "camel animal desert hump"],
  ["🐧", "penguin animal bird cold arctic"],
  ["🦋", "butterfly insect nature colorful"],
  ["🐝", "bee insect honey buzz pollinate"],
  ["🐛", "bug insect caterpillar worm"],
  ["🕷️", "spider insect web arachnid"],
  ["🐌", "snail slow shell garden"],
  ["🐬", "dolphin marine animal sea smart"],
  ["🐳", "whale marine animal sea large"],
  ["🦈", "shark marine animal sea predator"],
  ["🐙", "octopus marine animal sea tentacle"],
  // 👶 Family & People
  ["👶", "baby infant child family newborn"],
  ["👧", "girl child daughter kid"],
  ["👦", "boy child son kid"],
  ["👨‍👩‍👧", "family parents child household"],
  ["👪", "family parents children household"],
  ["👨‍👩‍👧‍👦", "family four parents kids"],
  ["🤰", "pregnant maternity baby expecting"],
  ["🎂", "birthday cake celebration party"],
  ["🎁", "gift present birthday holiday surprise"],
  ["💍", "ring engagement wedding marriage jewelry"],
  ["💒", "wedding chapel marriage ceremony"],
  ["💏", "couple kiss love romance"],
  ["👰", "bride wedding marriage ceremony"],
  ["🤵", "groom wedding marriage formal"],
  ["👩‍❤️‍👨", "couple love relationship heart"],
  ["🧓", "elder old senior grandparent"],
  ["👴", "grandpa grandfather old man senior"],
  ["👵", "grandma grandmother old woman senior"],
  ["🧒", "child kid young person"],
  ["🎉", "party celebration confetti birthday fun"],
  ["🎊", "confetti ball celebration party"],
  ["🥳", "party face celebration birthday hat"],
  ["🎈", "balloon party celebration decoration"],
  ["🎄", "christmas tree holiday xmas december"],
  ["🎃", "pumpkin halloween jack lantern october"],
  ["🕎", "menorah hanukkah jewish holiday candle"],
  ["🪔", "diya lamp light festival diwali"],
  ["🧧", "red envelope chinese new year lucky"],
  // 📱 Tech & Communication
  ["📱", "phone mobile smartphone cell device"],
  ["💻", "laptop computer device tech work"],
  ["🖨️", "printer print office document tech"],
  ["📞", "telephone phone call communication"],
  ["📶", "signal wifi internet bars connection"],
  ["📡", "satellite antenna signal communication"],
  ["🔋", "battery power charge energy device"],
  ["💾", "floppy disk save storage data"],
  ["📷", "camera photo photography picture"],
  ["🎥", "video camera film record"],
  ["📺", "television tv screen watch"],
  ["🖱️", "mouse computer click device"],
  ["⌨️", "keyboard typing computer device"],
  ["🖲️", "trackball computer input device"],
  ["💽", "minidisc storage data media"],
  ["📼", "vhs tape video cassette media"],
  ["📹", "camcorder video record camera"],
  ["🔍", "magnifying glass search find zoom"],
  ["🔎", "magnifying glass search find right"],
  ["🌐", "globe internet web world network"],
  ["📧", "email envelope message inbox"],
  ["📩", "inbox envelope message receive"],
  ["📨", "incoming envelope message mail"],
  ["💬", "speech bubble chat message talk"],
  ["📲", "mobile arrow phone incoming call"],
  ["📟", "pager beeper device old"],
  ["🔊", "speaker volume loud audio sound"],
  ["🔈", "speaker low volume audio sound"],
  // 🏛️ Government & Services
  ["🏛️", "government building official institution"],
  ["⚖️", "scales justice law legal court"],
  ["📜", "scroll document law certificate"],
  ["🗳️", "ballot vote election democracy"],
  ["🚔", "police car law enforcement"],
  ["🚒", "fire truck emergency rescue"],
  ["🚑", "ambulance emergency medical hospital"],
  ["📮", "mailbox post letter mail"],
  ["🏣", "post office mail service"],
  ["🏤", "european post office building mail"],
  ["🏪", "convenience store shop 24 open"],
  ["🏬", "department store shopping mall"],
  ["🏨", "hotel accommodation sleep travel"],
  ["🏩", "love hotel accommodation romance"],
  ["🏟️", "stadium arena sport event"],
  ["🏙️", "cityscape buildings urban skyline"],
  ["🌃", "night city buildings urban skyline"],
  ["🌆", "sunset cityscape buildings evening"],
  ["🛃", "customs border passport immigration"],
  ["🛂", "passport control immigration border"],
  // ⚡ Utilities & Symbols
  ["⚡", "lightning electricity power energy bolt"],
  ["💧", "water drop utility plumbing"],
  ["🔥", "fire hot flame gas heating"],
  ["♻️", "recycle green environment eco"],
  ["🌱", "seedling plant grow garden nature"],
  ["☀️", "sun solar sunshine weather energy"],
  ["❄️", "snowflake cold winter freeze ice"],
  ["🌡️", "thermometer temperature weather heat"],
  ["🚫", "prohibited no block forbidden ignore"],
  ["⭐", "star favorite important gold"],
  ["✅", "check mark done complete approved"],
  ["❌", "cross reject cancel remove delete"],
  ["🔔", "bell notification alert reminder"],
  ["🔒", "lock security password private safe"],
  ["📌", "pin pushpin location bookmark mark"],
  ["🏷️", "tag label price sale category"],
  ["❓", "question mark help unknown what"],
  ["❗", "exclamation mark important alert warning"],
  ["⚠️", "warning caution danger alert triangle"],
  ["💯", "hundred percent score perfect"],
  ["🗑️", "trash can delete garbage waste bin"],
  ["✂️", "scissors cut trim tool"],
  ["📦", "package box shipping delivery parcel"],
  ["🔗", "link chain url connection"],
  ["🏴", "black flag pirate skull"],
  ["🏳️", "white flag surrender peace"],
  ["🇮🇱", "israel flag country"],
  ["🇺🇸", "usa america flag country"],
  ["🇬🇧", "uk britain flag country england"],
  ["🇪🇺", "european union flag eu"],
  ["🔄", "arrows cycle refresh reload update"],
  ["⏰", "alarm clock time morning wake"],
  ["⏱️", "stopwatch timer time speed"],
  ["🕐", "clock one time oclock hour"],
  ["📆", "calendar date schedule plan month"],
  ["📅", "calendar date event schedule"],
  ["🗓️", "calendar spiral date schedule plan"],
  ["✨", "sparkles magic new shiny clean"],
  ["💫", "dizzy star shooting sparkle"],
  ["🎗️", "ribbon awareness cancer support"],
  ["🔮", "crystal ball fortune magic predict"],
  ["🧿", "evil eye nazar blue protection"],
  ["🪬", "hamsa hand protection luck"],
  ["♠️", "spade card suit game black"],
  ["♥️", "heart card suit game red"],
  ["♦️", "diamond card suit game red"],
  ["♣️", "club card suit game black"],
  ["🀄", "mahjong game tile chinese"],
  ["🎴", "hanafuda card game japanese"],
  // 🏠 Real Estate & Property
  ["🏚️", "derelict house abandoned building old"],
  ["🪨", "rock stone nature boulder"],
  ["⛲", "fountain water park garden"],
  ["🌉", "bridge night city travel structure"],
  ["🌁", "foggy bridge san francisco city"],
  // 🧸 Kids & Toys
  ["🧸", "teddy bear toy stuffed animal kids plush cute"],
  ["🪀", "yo-yo toy play kids"],
  ["🪁", "kite toy play wind outdoor kids"],
  ["🎎", "dolls japanese festival decoration"],
  ["🪆", "nesting dolls russian matryoshka toy"],
  ["🎐", "wind chime decoration bell sound"],
  // 📐 Math & Science
  ["🧮", "abacus counting math calculate"],
  ["🔢", "numbers input 1234 math"],
  ["🔣", "symbols input special characters"],
  ["🧫", "petri dish science biology lab"],
  ["🔭", "telescope astronomy space star science"],
  ["⚗️", "alembic chemistry science distill lab"],
  ["⚛️", "atom physics science nuclear"],
];

export function Categories() {
  const queryClient = useQueryClient();
  const [isAddCategoryOpen, setIsAddCategoryOpen] = useState(false);
  const [isAddTagOpen, setIsAddTagOpen] = useState<{ category: string } | null>(
    null,
  );
  const [isRelocateOpen, setIsRelocateOpen] = useState<{
    category: string;
    tag: string;
  } | null>(null);
  const [editingIcon, setEditingIcon] = useState<{
    category: string;
    currentIcon: string;
  } | null>(null);
  const [tempIcon, setTempIcon] = useState("");
  const [emojiSearch, setEmojiSearch] = useState("");

  const { data: categories, isLoading } = useQuery({
    queryKey: ["categories"],
    queryFn: () => taggingApi.getCategories().then((res) => res.data),
  });

  const { data: icons } = useQuery({
    queryKey: ["category-icons"],
    queryFn: () => taggingApi.getIcons().then((res) => res.data),
  });

  const createCategoryMutation = useMutation({
    mutationFn: (name: string) => taggingApi.createCategory(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setIsAddCategoryOpen(false);
    },
  });

  const deleteCategoryMutation = useMutation({
    mutationFn: (name: string) => taggingApi.deleteCategory(name),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["categories"] }),
  });

  const createTagMutation = useMutation({
    mutationFn: ({ category, tag }: { category: string; tag: string }) =>
      taggingApi.createTag(category, tag),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setIsAddTagOpen(null);
    },
  });

  const deleteTagMutation = useMutation({
    mutationFn: ({ category, tag }: { category: string; tag: string }) =>
      taggingApi.deleteTag(category, tag),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["categories"] }),
  });

  const relocateTagMutation = useMutation({
    mutationFn: ({ tag, newCategory, oldCategory }: any) =>
      taggingApi.relocateTag(oldCategory, newCategory, tag),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setIsRelocateOpen(null);
    },
  });

  const updateIconMutation = useMutation({
    mutationFn: ({ category, icon }: { category: string; icon: string }) =>
      taggingApi.updateIcon(category, icon),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["category-icons"] });
      setEditingIcon(null);
    },
  });

  if (isLoading)
    return (
      <div className="space-y-8 p-8">
        <Skeleton variant="text" lines={2} className="w-64" />
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          <Skeleton variant="card" className="h-48" />
          <Skeleton variant="card" className="h-48" />
          <Skeleton variant="card" className="h-48" />
          <Skeleton variant="card" className="h-48" />
          <Skeleton variant="card" className="h-48" />
          <Skeleton variant="card" className="h-48" />
        </div>
      </div>
    );

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Categories & Tags</h1>
          <p className="text-[var(--text-muted)] mt-1">
            Manage your expense classification and tagging logic
          </p>
        </div>
        <button
          onClick={() => setIsAddCategoryOpen(true)}
          className="flex items-center gap-2 px-6 py-2.5 bg-[var(--primary)] text-white rounded-xl font-bold shadow-lg shadow-[var(--primary)]/20 hover:bg-[var(--primary-dark)] transition-all"
        >
          <Plus size={18} /> New Category
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
        {categories &&
          Object.entries(categories as Record<string, string[]>)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(
            ([category, tags]) => (
              <div
                key={category}
                className="group bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-6 shadow-sm hover:shadow-xl transition-all flex flex-col"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => {
                        const currentIcon = icons?.[category] || "💰";
                        setEditingIcon({ category, currentIcon });
                        setTempIcon(currentIcon);
                        setEmojiSearch("");
                      }}
                      className="p-2.5 rounded-xl bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-all text-xl w-11 h-11 flex items-center justify-center border border-blue-500/20"
                      title="Change Icon"
                    >
                      {icons?.[category] || <Wallet size={20} />}
                    </button>
                    <h3 className="font-bold text-lg text-white">{category}</h3>
                  </div>
                  <button
                    onClick={() => {
                      if (
                        window.confirm(
                          `Delete category "${category}"? All associated tags will be nullified in existing transactions.`,
                        )
                      ) {
                        deleteCategoryMutation.mutate(category);
                      }
                    }}
                    className="p-2 rounded-lg hover:bg-red-500/10 text-[var(--text-muted)] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>

                <div className="flex-1 space-y-2">
                  <div className="flex flex-wrap gap-2">
                    {tags.map((tag) => (
                      <div
                        key={tag}
                        className="group/tag flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 transition-all"
                      >
                        <span className="text-sm font-medium text-[var(--text-muted)]">
                          {tag}
                        </span>
                        <div className="flex items-center gap-0.5 opacity-0 group-hover/tag:opacity-100 transition-all ml-1">
                          <button
                            onClick={() => setIsRelocateOpen({ category, tag })}
                            className="p-1 hover:bg-blue-500/10 text-blue-400 rounded transition-colors"
                            title="Relocate Tag"
                          >
                            <MoveRight size={12} />
                          </button>
                          <button
                            onClick={() => {
                              if (
                                window.confirm(
                                  `Delete tag "${tag}" from "${category}"? It will be removed from all existing transactions.`,
                                )
                              ) {
                                deleteTagMutation.mutate({ category, tag });
                              }
                            }}
                            className="p-1 hover:bg-red-500/10 text-red-400 rounded transition-colors"
                            title="Delete Tag"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                  {tags.length === 0 && (
                    <div className="text-xs text-[var(--text-muted)] italic py-2">
                      No tags defined
                    </div>
                  )}
                </div>

                <button
                  onClick={() => setIsAddTagOpen({ category })}
                  className="mt-6 flex items-center justify-center gap-2 py-2 rounded-xl border border-dashed border-[var(--surface-light)] text-xs font-bold text-[var(--text-muted)] hover:border-[var(--primary)]/50 hover:text-[var(--primary)] transition-all"
                >
                  <Plus size={14} /> Add Tag
                </button>
              </div>
            ),
          )}
      </div>

      {/* Modals */}
      {isAddCategoryOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-6 shadow-2xl w-full max-w-sm animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-4">Create New Category</h3>
            <input
              autoFocus
              type="text"
              placeholder="Category Name"
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] mb-6 transition-all"
              onKeyDown={(e) => {
                if (e.key === "Enter")
                  createCategoryMutation.mutate(
                    (e.target as HTMLInputElement).value,
                  );
                if (e.key === "Escape") setIsAddCategoryOpen(false);
              }}
            />
            <div className="flex gap-3">
              <button
                onClick={() => setIsAddCategoryOpen(false)}
                className="flex-1 py-2 text-sm font-bold hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={(e) => {
                  const val = (
                    e.currentTarget.parentElement
                      ?.previousElementSibling as HTMLInputElement
                  ).value;
                  if (val) createCategoryMutation.mutate(val);
                }}
                className="flex-1 py-2 bg-[var(--primary)] rounded-xl text-white font-bold hover:bg-[var(--primary-dark)] transition-all"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {isAddTagOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-6 shadow-2xl w-full max-w-sm animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-4">
              Add Tag to{" "}
              <span className="text-[var(--primary)]">
                {isAddTagOpen.category}
              </span>
            </h3>
            <input
              autoFocus
              type="text"
              placeholder="Tag Name"
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] mb-6 transition-all"
              onKeyDown={(e) => {
                if (e.key === "Enter")
                  createTagMutation.mutate({
                    category: isAddTagOpen.category,
                    tag: (e.target as HTMLInputElement).value,
                  });
                if (e.key === "Escape") setIsAddTagOpen(null);
              }}
            />
            <div className="flex gap-3">
              <button
                onClick={() => setIsAddTagOpen(null)}
                className="flex-1 py-2 text-sm font-bold hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={(e) => {
                  const val = (
                    e.currentTarget.parentElement
                      ?.previousElementSibling as HTMLInputElement
                  ).value;
                  if (val)
                    createTagMutation.mutate({
                      category: isAddTagOpen.category,
                      tag: val,
                    });
                }}
                className="flex-1 py-2 bg-[var(--primary)] rounded-xl text-white font-bold hover:bg-[var(--primary-dark)] transition-all"
              >
                Add Tag
              </button>
            </div>
          </div>
        </div>
      )}

      {isRelocateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-6 shadow-2xl w-full max-w-sm animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-2">Relocate Tag</h3>
            <p className="text-sm text-[var(--text-muted)] mb-6">
              Move{" "}
              <span className="font-bold text-white">
                "{isRelocateOpen.tag}"
              </span>{" "}
              to a different category
            </p>

            <div className="space-y-2 max-h-[200px] overflow-y-auto mb-6 pr-2">
              {categories &&
                Object.keys(categories)
                  .filter((c) => c !== isRelocateOpen.category)
                  .map((cat) => (
                    <button
                      key={cat}
                      onClick={() =>
                        relocateTagMutation.mutate({
                          tag: isRelocateOpen.tag,
                          oldCategory: isRelocateOpen.category,
                          newCategory: cat,
                        })
                      }
                      className="w-full text-left px-4 py-3 rounded-xl bg-[var(--surface-base)] hover:bg-[var(--primary)]/10 border border-transparent hover:border-[var(--primary)]/30 transition-all font-bold group"
                    >
                      <div className="flex items-center justify-between">
                        <span>{cat}</span>
                        <MoveRight
                          size={16}
                          className="opacity-0 group-hover:opacity-100 transition-all"
                        />
                      </div>
                    </button>
                  ))}
            </div>

            <button
              onClick={() => setIsRelocateOpen(null)}
              className="w-full py-2 text-sm font-bold hover:text-white transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {editingIcon && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-6 shadow-2xl w-full max-w-md animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-4">
              Change Icon for{" "}
              <span className="text-[var(--primary)]">
                {editingIcon.category}
              </span>
            </h3>

            <div className="space-y-6">
              {/* Search */}
              <div className="relative">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                <input
                  type="text"
                  placeholder="Search emojis... (e.g. food, car, health)"
                  value={emojiSearch}
                  onChange={(e) => setEmojiSearch(e.target.value)}
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl pl-9 pr-4 py-2 text-sm outline-none focus:border-[var(--primary)] transition-all"
                />
              </div>

              {/* Emoji Grid */}
              <div>
                {(() => {
                  const query = emojiSearch.toLowerCase().trim();
                  const filtered = query
                    ? EMOJI_DATA.filter(([, kw]) => kw.includes(query))
                    : EMOJI_DATA;
                  return filtered.length > 0 ? (
                    <div className="grid grid-cols-8 gap-2 max-h-[280px] overflow-y-auto p-1">
                      {filtered.map(([emoji]) => (
                        <button
                          key={emoji}
                          onClick={() => setTempIcon(emoji)}
                          className={`w-10 h-10 flex items-center justify-center rounded-lg bg-[var(--surface-base)] border transition-all text-xl ${
                            tempIcon === emoji
                              ? "border-[var(--primary)] bg-[var(--primary)]/20"
                              : "border-[var(--surface-light)] hover:border-[var(--primary)] hover:bg-[var(--primary)]/10"
                          }`}
                        >
                          {emoji}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-[var(--text-muted)] text-center py-6">
                      No emojis match &ldquo;{emojiSearch}&rdquo;
                    </p>
                  );
                })()}
              </div>

              {/* Custom Input */}
              <div>
                <p className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider mb-3">
                  Custom Emoji or Text
                </p>
                <input
                  type="text"
                  maxLength={4}
                  value={tempIcon}
                  onChange={(e) => setTempIcon(e.target.value)}
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 text-2xl text-center outline-none focus:border-[var(--primary)] transition-all"
                  onKeyDown={(e) => {
                    if (e.key === "Enter")
                      updateIconMutation.mutate({
                        category: editingIcon.category,
                        icon: tempIcon,
                      });
                    if (e.key === "Escape") setEditingIcon(null);
                  }}
                />
              </div>
            </div>

            <div className="flex gap-3 mt-8">
              <button
                onClick={() => setEditingIcon(null)}
                className="flex-1 py-2 text-sm font-bold hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (tempIcon)
                    updateIconMutation.mutate({
                      category: editingIcon.category,
                      icon: tempIcon,
                    });
                }}
                className="flex-1 py-2 bg-[var(--primary)] rounded-xl text-white font-bold hover:bg-[var(--primary-dark)] transition-all"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
