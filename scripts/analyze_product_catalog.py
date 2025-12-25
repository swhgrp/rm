#!/usr/bin/env python3
"""
Analyze product catalog CSV and compare against existing inventory vendor items.
"""

import csv
import io
import psycopg2
from psycopg2.extras import RealDictCursor

INVENTORY_DB = {
    'host': 'inventory-db',
    'database': 'inventory_db',
    'user': 'inventory_user',
    'password': 'inventory_pass'
}

# Vendor name mapping from CSV to inventory vendor_id
VENDOR_MAPPING = {
    'Gold Coast Beverage, LLC': 9,
    'Southern Eagle Distributing, Inc.': 8,
    'Southern Glazer\'s Wine & Spirits of FL': 6,
    '(Western Beverage DBA Double Eagle Distributing)': 5,
    'Premier Beverage Co.dba Breakthru Beverage Florida': 7,
    'Republic National Dist - Deerfield Bch.': 10,
}

# Items to skip (deposits, credits, misc)
SKIP_PATTERNS = [
    'EMPTY', 'OVERPAYMENT', 'NSF FEE', 'FREIGHT', 'DELIVERY CHARGE',
    'MISCELLANEOUS', 'MISC COASTERS', 'SUMMARY LEVEL', '----',
    'CR OVERPYMNT', 'POS EMPTY'
]

CSV_DATA = """Distributor Name,Distributor Item Number,Product Description
"Gold Coast Beverage, LLC",64213,SUN CRUISER LEMONADE PLUS ICED TEA P
"Gold Coast Beverage, LLC",42856,HEINEKEN 0.0  C24 11.2OZ 6P
"Gold Coast Beverage, LLC",50434,YUENGLING FLIGHT  C24 16OZ 6P
"Gold Coast Beverage, LLC",63780,MAMITAS VARIETY PACK C24 12OZ 8P
"Gold Coast Beverage, LLC",17909,BLUE MOON BELGIAN WHEAT C24 16OZ 4P
"Gold Coast Beverage, LLC",10302,HEINEKEN C24 16OZ 4P
"Gold Coast Beverage, LLC",31915,WC HRD BLK CHR C24 12OZ 6PSL
"Gold Coast Beverage, LLC",41370,WC HRD MANGO C24 12OZ 6PSL
"Gold Coast Beverage, LLC",33778,YUENG LGR C24 16OZ 6P
"Gold Coast Beverage, LLC",11461,YUENGLING LAGER K 1/2BBL
"Gold Coast Beverage, LLC",21349,ANGRY ORCHARD CRISP APPLE C24 16OZ
"Gold Coast Beverage, LLC",11137,TWISTED TEA ORIGINAL C24 12OZ 12P
"Gold Coast Beverage, LLC",51318,TRULY STRAWBERRY LEMONADE C24 12OZ 6
"Gold Coast Beverage, LLC",14889,COORS LIGHT  A24 16OZ LSE
"Gold Coast Beverage, LLC",11557,LITE  A24 16OZ LSE
"Gold Coast Beverage, LLC",00161,POS EMPTY KEG $35 MISCELLANEOUS
"Gold Coast Beverage, LLC",00998,Overpayment
"Gold Coast Beverage, LLC",65814,SUN CRUISER LEMONADE PLUS ICED TEA P
"Gold Coast Beverage, LLC",40585,FUNKY BUDDHA FLORIDIAN C24 16OZ
"Gold Coast Beverage, LLC",46094,WHITE CLAW HARD SELTZER MANGO C24 16
"Gold Coast Beverage, LLC",14857,COORS LIGHT  A18 16OZ 9P
"Gold Coast Beverage, LLC",56874,WATERBIRD VODKA TRANSFUSION C24 12OZ
"Gold Coast Beverage, LLC",12563,ATHLETIC NA RUN WILD IPA C24 12OZ 6P
"Gold Coast Beverage, LLC",57229,ATHLETIC NA RUN WILD IPA C24 12OZ 12
"Gold Coast Beverage, LLC",17809,LITE  A15 16OZ
"Gold Coast Beverage, LLC",64211,SUN CRUISER ICED TEA PLUS VODKA VARI
"Gold Coast Beverage, LLC",67069,SUN CRUISER VODKA PINK LEMONADE C24
"Gold Coast Beverage, LLC",59711,WATERBIRD VODKA TRANSFUSION C12 24OZ
"Gold Coast Beverage, LLC",46194,LAGUNITAS IPA C24 12OZ 12P
"Gold Coast Beverage, LLC",62430,MODELO ESP C24 16OZ 4P
"Gold Coast Beverage, LLC",62428,CORONA C24 16OZ 4P
"Gold Coast Beverage, LLC",11319,CORONA EXTRA  C24 12OZ 12PSL
"Gold Coast Beverage, LLC",10170,MODELO ESP C24 12OZ 12P
"Gold Coast Beverage, LLC",63779,MAMITAS COCKTAIL VARIETY C24 12OZ 8P
"Southern Eagle Distributing, Inc.",8325,SURFSIDE LEMONADE & VODKA 4PK 12OZ CAN
"Southern Eagle Distributing, Inc.",8322,SURFSIDE ICED TEA & VODKA 4PK 12OZ CAN
"Southern Eagle Distributing, Inc.",10526,FIREBALL CINNAMON MALT WALMART 120PK 50ML PLASTIC BOTTLE
"Southern Eagle Distributing, Inc.",8336,SURFSIDE STRAWBERRY LEMONADE & VODKA 4PK 12OZ CAN
"Southern Eagle Distributing, Inc.",250,BUD LIGHT 20PK 16OZ ALUM BOTTLE
"Southern Eagle Distributing, Inc.",10378,NUTRL WATERMELON VODKA SODA 4PK 12OZ CAN
"Southern Eagle Distributing, Inc.",10377,NUTRL PINEAPPLE VODKA SODA 4PK 12OZ CAN
"Southern Eagle Distributing, Inc.",160,BUDWEISER 12PK 16OZ ALUM BOTTLE
"Southern Eagle Distributing, Inc.",852,MICHELOB ULTRA 1/2 KEG
"Southern Eagle Distributing, Inc.",952,EMPTY AB 1/2 K 35
"Southern Eagle Distributing, Inc.",134,BUDWEISER ZERO 12PK 12OZ CAN
"Southern Eagle Distributing, Inc.",5545,STELLA ARTOIS 4PK 16OZ CAN
"Southern Eagle Distributing, Inc.",5546,STELLA ARTOIS 6PK 16OZ CAN
"Southern Eagle Distributing, Inc.",32057,CIGAR CITY JAI ALAI IPA 2/12PK 16OZ CAN
"Southern Eagle Distributing, Inc.",260,BUD LIGHT 12PK 16OZ ALUM BOTTLE
"Southern Eagle Distributing, Inc.",4860,MICHELOB ULTRA 12PK 16OZ ALUM BOTTLE
"Southern Eagle Distributing, Inc.",32610,CIGAR CITY JAI ALAI IPA 12PK 12OZ CAN
"Southern Eagle Distributing, Inc.",8324,SURFSIDE ICED TEA LEMONADE & VODKA 4PK 12OZ CAN
Southern Glazer's Wine & Spirits of FL,000041175,CLICQUOT YELLOW LABEL BRUT 750ML
Southern Glazer's Wine & Spirits of FL,000541053,CAZADORES CKTL SP MAR11.8CAN PAD4P 355ML
Southern Glazer's Wine & Spirits of FL,000552675,SUTTER HOME PINOT GRIGIO PET 6/4PK 187ML
Southern Glazer's Wine & Spirits of FL,000534577,BACARDI CKTL(RUM/BAH/PIN)CAN4/6PAD 355ML
Southern Glazer's Wine & Spirits of FL,000128213,SUTTER HOME CHARDONNAY PET 6/4PK 187ML
Southern Glazer's Wine & Spirits of FL,000981374,MULE 2.0 MEXICAN MULE CAN 6/4PK 355ML
Southern Glazer's Wine & Spirits of FL,000981377,MULE 2.0 CARIBE MULE CAN 6/4PK 355ML
Southern Glazer's Wine & Spirits of FL,000992820,HORNITOS TEQ SELTZ LIME CAN 6/4PK 355ML
Southern Glazer's Wine & Spirits of FL,000984915,BACARDI CKTL BAHAMA MAMA 11.8CAN4P
Southern Glazer's Wine & Spirits of FL,0,Summary Level Adjustments
Southern Glazer's Wine & Spirits of FL,000552674,SUTTER HOME MERLOT PET 6/4PK 187ML
Southern Glazer's Wine & Spirits of FL,000552909,SUTTER HOME CHARDONNAY PET 6/4PK 187ML
Southern Glazer's Wine & Spirits of FL,000970726,BACARDI CKTL RUM PUNCH 11.8 CAN6/4 355ML
Southern Glazer's Wine & Spirits of FL,000541052,CAZADORES CKTL MARG 11.8 CAN PAD4P 355ML
Southern Glazer's Wine & Spirits of FL,000984914,BACARDI CKTL MOJITO 11.8 CAN6/4P 355ML
Southern Glazer's Wine & Spirits of FL,000552673,SUTTER HOME SAUV BLANC PET 6/4PK 187ML
Southern Glazer's Wine & Spirits of FL,000603439,RUFFINO PROSECCO LUMINA(SC)LSE 187ML
Southern Glazer's Wine & Spirits of FL,000632627,CAZADORES CKTL PALOMA10CAN PAD(104 355ML
Southern Glazer's Wine & Spirits of FL,000632633,CAZADORES CKTL MARG 10 CAN PAD(104 355ML
Southern Glazer's Wine & Spirits of FL,000552907,SUTTER HOME CAB SAUV PET 6/4PK 187ML
(Western Beverage DBA Double Eagle Distributing),06417,HD HARD TEA VA 2/12/12 CN
(Western Beverage DBA Double Eagle Distributing),09050,EMPTY AB 1/4 BBL
(Western Beverage DBA Double Eagle Distributing),00629,BUD LT 24/16 CALNR
(Western Beverage DBA Double Eagle Distributing),08585,MODELO 6/4/16 CN
(Western Beverage DBA Double Eagle Distributing),06655,NUTRL FRUIT VP 3/8/12 CN
(Western Beverage DBA Double Eagle Distributing),00504,MICH ULTRA 2/12/16 CALNR
(Western Beverage DBA Double Eagle Distributing),08286,CORONA 6/4/16 CN
(Western Beverage DBA Double Eagle Distributing),04515,STELLA ARTOIS 6/4/16 CN
(Western Beverage DBA Double Eagle Distributing),00917,BUD LT 1/6 BBL
(Western Beverage DBA Double Eagle Distributing),00958,BUD LT 1/2 BBL
(Western Beverage DBA Double Eagle Distributing),09040,EMPTY AB 1/2 BBL
(Western Beverage DBA Double Eagle Distributing),09018,EMPTY STELLA 13.2 GAL
(Western Beverage DBA Double Eagle Distributing),09055,EMPTY AB 1/6 BBL
(Western Beverage DBA Double Eagle Distributing),04451,STELLA ARTOIS 13.2 GAL BBL
(Western Beverage DBA Double Eagle Distributing),02041,GI IPA 1/2 BBL
(Western Beverage DBA Double Eagle Distributing),00965,MIC AMBER BOCK 1/2 BBL
(Western Beverage DBA Double Eagle Distributing),00646,BUD LT 2/12/16 CALNR
(Western Beverage DBA Double Eagle Distributing),08280,CORONA 2/12/12 CN
(Western Beverage DBA Double Eagle Distributing),00046,BUD 2/12/16 CALNR
(Western Beverage DBA Double Eagle Distributing),09033,EMPTY TENNENTS 13.2 GAL
(Western Beverage DBA Double Eagle Distributing),05931,DDT-BLANCO 1/750 ML NR
(Western Beverage DBA Double Eagle Distributing),05934,DDT-COFFEE REP 1/750 ML
(Western Beverage DBA Double Eagle Distributing),05930,DDT-PINEAP JAL 1/750 ML NR
(Western Beverage DBA Double Eagle Distributing),05932,DDT-REPOSADO 1/750 ML NR
(Western Beverage DBA Double Eagle Distributing),00501,MICH ULTRA 24/16 CALNR
(Western Beverage DBA Double Eagle Distributing),06652,NUTRL WATERMEL 6/4/12 CN
(Western Beverage DBA Double Eagle Distributing),00531,MUL ZERO 2/12/12 CN
(Western Beverage DBA Double Eagle Distributing),08945,MODELO CH LIMO 6/4/16 CN
(Western Beverage DBA Double Eagle Distributing),00997,------------------------------------
(Western Beverage DBA Double Eagle Distributing),00653,BUD LT 24/16 CN
(Western Beverage DBA Double Eagle Distributing),00029,BUD 24/16 CALNR
(Western Beverage DBA Double Eagle Distributing),06659,NUTRL ORANGE 6/4/12 CN
(Western Beverage DBA Double Eagle Distributing),06656,NUTRL LEMON VP 3/8/12 CN
(Western Beverage DBA Double Eagle Distributing),08771,CORONA PREMIER 18/12OZ CN
(Western Beverage DBA Double Eagle Distributing),04512,STELLA ARTOIS 2/12/12 CN
(Western Beverage DBA Double Eagle Distributing),08100,MISC COASTERS
"Gold Coast Beverage, LLC",00998,Overpayment
"Gold Coast Beverage, LLC",51459,HEINEKEN 0.0  C24 11.2OZ 12P
"Gold Coast Beverage, LLC",38923,NEW BELGIUM VOODOO RANGER JUICY HAZE
"Gold Coast Beverage, LLC",13234,DOS EQUIS LAGER C24 12OZ 12P
"Gold Coast Beverage, LLC",57229,ATHLETIC NA RUN WILD IPA C24 12OZ 12
"Gold Coast Beverage, LLC",63459,SURFSIDE VODKA TEA C24 12OZ 4PSL
"Gold Coast Beverage, LLC",63460,SURFSIDE VODKA LEMONADE C24 12OZ 4PS
"Gold Coast Beverage, LLC",66704,SUN CRUISER VODKA LEMONADE C24 12OZ
"Gold Coast Beverage, LLC",61518,SUN CRUISER CLASSIC ICED TEA PLUS VO
"Gold Coast Beverage, LLC",63589,SURFSIDE PEACH TEA VODKA C24 12OZ 4P
"Gold Coast Beverage, LLC",64804,SURFSIDE RASPBERRY TEA AND VODKA C24
"Gold Coast Beverage, LLC",11462,YUENGLING LAGER K 1/4BBL
"Gold Coast Beverage, LLC",17810,COORS LIGHT  A15 16OZ
"Gold Coast Beverage, LLC",45952,WHITE CLAW HARD SELTZER MANGO C24 12
"Gold Coast Beverage, LLC",31915,WC HRD BLK CHR C24 12OZ 6PSL
"Gold Coast Beverage, LLC",10218,COORS LIGHT  K 1/4BBL
"Gold Coast Beverage, LLC",12562,ATHLETIC NA CERVEZA C24 12OZ 6P
"Gold Coast Beverage, LLC",63670,SURFSIDE HALF AND HALF ICED TEA LEMO
"Gold Coast Beverage, LLC",60718,NO DAYS OFF SPARKLING WATER C12 16OZ
"Gold Coast Beverage, LLC",60904,SURFSIDE VODKA LEMONADE STRAWBERRY C
"Gold Coast Beverage, LLC",000,Cr overpymnt orig inv 100654501
"Gold Coast Beverage, LLC",0000,NSF FEE
"Gold Coast Beverage, LLC",00000,Cr overpymnt orig inv 100655328
"Gold Coast Beverage, LLC",38060,CIGAR CITY JAI ALAI IPA C24 16OZ
"Gold Coast Beverage, LLC",14889,COORS LIGHT  A24 16OZ LSE
"Gold Coast Beverage, LLC",11557,LITE  A24 16OZ LSE
"Gold Coast Beverage, LLC",10302,HEINEKEN C24 16OZ 4P
"Gold Coast Beverage, LLC",42856,HEINEKEN 0.0  C24 11.2OZ 6P
"Gold Coast Beverage, LLC",33778,YUENG LGR C24 16OZ 6P
"Gold Coast Beverage, LLC",11461,YUENGLING LAGER K 1/2BBL
"Gold Coast Beverage, LLC",50434,YUENGLING FLIGHT  C24 16OZ 6P
"Gold Coast Beverage, LLC",00161,POS EMPTY KEG $35 MISCELLANEOUS
Premier Beverage Co.dba Breakthru Beverage Florida,9006996,RED BULL 8.4Z
Premier Beverage Co.dba Breakthru Beverage Florida,9697925,HIGH NOON CKTL TEQ LIME CAN 6/4PK 355ML
Premier Beverage Co.dba Breakthru Beverage Florida,9734191,RED BULL SUGAR FREE WTRMLN CAN 24PK 8.4Z
Premier Beverage Co.dba Breakthru Beverage Florida,9601528,RED BULL WTRMLN 6/4PK 8.4Z
Premier Beverage Co.dba Breakthru Beverage Florida,9360505,RED BULL YELLOW 24PK 8.4Z
Premier Beverage Co.dba Breakthru Beverage Florida,9031406,FIREBALL CINN WHSKY 1L
Premier Beverage Co.dba Breakthru Beverage Florida,9006278,REAL COCO CRM COCO 12B 16.9Z
Premier Beverage Co.dba Breakthru Beverage Florida,9637414,HIGH NOON CKTL PINEAPL LOOSE CN 24P 355M
Premier Beverage Co.dba Breakthru Beverage Florida,9690725,HIGH NOON CKTL BLK CHRY CAN 24PK 355ML
Premier Beverage Co.dba Breakthru Beverage Florida,9690713,HIGH NOON CKTL GRPFRT CAN 24PK 355ML
Premier Beverage Co.dba Breakthru Beverage Florida,9709727,HIGH NOON CKTL TEQ LIME CAN 24PK 355ML
Premier Beverage Co.dba Breakthru Beverage Florida,9637229,HIGH NOON CKTL WTRMLN LOOSE CAN 24P 355M
Premier Beverage Co.dba Breakthru Beverage Florida,9367378,HIGH NOON CKTL WTRMLN CAN 6/4PK 355ML
Premier Beverage Co.dba Breakthru Beverage Florida,9376399,MILAGRO TEQ SLVR 6B 1L
Premier Beverage Co.dba Breakthru Beverage Florida,9247652,REAL PSNFRT NA PET 6B 16.9Z
Premier Beverage Co.dba Breakthru Beverage Florida,9247658,REAL RASPB NA PET 6B 16.9Z
Premier Beverage Co.dba Breakthru Beverage Florida,22137,JACK DANIELS BLK 1L
Premier Beverage Co.dba Breakthru Beverage Florida,9031151,Delivery Charge
Premier Beverage Co.dba Breakthru Beverage Florida,9001723,HENDRICKS GIN 6B 1L
Premier Beverage Co.dba Breakthru Beverage Florida,21733,WOODFORD RSV BRBN 6B 1L
Premier Beverage Co.dba Breakthru Beverage Florida,9698017,HIGH NOON CKTL TEQ GRPFRT CAN 6/4P 355ML
Premier Beverage Co.dba Breakthru Beverage Florida,9449119,RED BULL WTRMLN 24PK 8.4Z
Premier Beverage Co.dba Breakthru Beverage Florida,9158089,RED BULL BLUE 24B 8.4Z
Premier Beverage Co.dba Breakthru Beverage Florida,9367376,HIGH NOON CKTL PINEAPL CAN 6/4PK 355ML
Premier Beverage Co.dba Breakthru Beverage Florida,9367380,HIGH NOON CKTL BLK CHRY CAN 6/4PK 355ML
Premier Beverage Co.dba Breakthru Beverage Florida,9367379,HIGH NOON CKTL GRPFRT CAN 6/4PK 355ML
Premier Beverage Co.dba Breakthru Beverage Florida,9006995,RED BULL SUGAR FREE 8.4Z
Republic National Dist - Deerfield Bch.,00358931,SANTA MARG ALTO ADIGE P GRIGIO
Republic National Dist - Deerfield Bch.,00455922,FOREST FL DIRTY MARTINI
Republic National Dist - Deerfield Bch.,00363003,ST FRANCIS CHARD +14
Republic National Dist - Deerfield Bch.,00363007,SANTA MARG ITALY P GRIGIO TRAY
Republic National Dist - Deerfield Bch.,99999999,FREIGHT
Republic National Dist - Deerfield Bch.,00012427,JC ESP SILVER TEQ
Republic National Dist - Deerfield Bch.,00294864,MACALLAN SHERRY OAK 12YR NEW UPC
Republic National Dist - Deerfield Bch.,00116278,DON Q GR RSV ANEJO XO RUM 6PK
Republic National Dist - Deerfield Bch.,00115955,DON Q RSV 7 RUM 6PK
Republic National Dist - Deerfield Bch.,00999837,MACALLAN DBL CSK 12YR
Republic National Dist - Deerfield Bch.,00241495,EMPRESS 1908 GIN 6PK
Republic National Dist - Deerfield Bch.,03253511,STOLLER FMLY EST WLMET P NOIR SCRW CP
Republic National Dist - Deerfield Bch.,03391019,SANTA MARG ITALY P GRIGIO
Republic National Dist - Deerfield Bch.,00134592,REGATTA GINGER BEER 4X6 CN
Republic National Dist - Deerfield Bch.,00142767,J LOHR RIVERSTONE CHARD NL
Republic National Dist - Deerfield Bch.,00433157,LUC BELAIRE RARE LUXE CUVEE 6PK
Republic National Dist - Deerfield Bch.,00065313,OPERA PRIMA BLUE SPRK MOSCATO
Republic National Dist - Deerfield Bch.,00065891,SANTA MARG PROSECCO 12PK  NUPC NL
Republic National Dist - Deerfield Bch.,00107302,DON Q COCO RUM NL
Republic National Dist - Deerfield Bch.,00127110,SOUTH BCH ORG BL AGAVE NECTAR 12PK
Republic National Dist - Deerfield Bch.,00109109,DON Q CRISTAL RUM NL
Republic National Dist - Deerfield Bch.,00107305,DON Q PASION RUM NL
Republic National Dist - Deerfield Bch.,00109162,DON Q PINA RUM NL
Republic National Dist - Deerfield Bch.,00202797,FOUR ROSES BBN
Republic National Dist - Deerfield Bch.,00431445,LUC BELAIRE RARE ROSE 6PK OLD
Republic National Dist - Deerfield Bch.,00063627,STAVE & STEEL BBN BRL AGED CAB
Republic National Dist - Deerfield Bch.,00242157,J LOHR RIVERSTONE CHARD NL REST
Republic National Dist - Deerfield Bch.,00514644,MASI MASIANCO P GRIGIO
Republic National Dist - Deerfield Bch.,03413549,MACALLAN DBL CSK 12YR 2025
Republic National Dist - Deerfield Bch.,00151285,SOUTH BCH ORG BL AGAVE NECTAR 4PK
Southern Glazer's Wine & Spirits of FL,000557367,APEROL APERITIVO 22 1.0L
Southern Glazer's Wine & Spirits of FL,000294498,MAKERS 46 BOURBON 94 750ML
Southern Glazer's Wine & Spirits of FL,000009999,MAKERS MARK BOURBON 90 750ML
Southern Glazer's Wine & Spirits of FL,000183981,DAILYS SIMPLE SYRUP 1.0L
Southern Glazer's Wine & Spirits of FL,000025213,DEKUYPER PEACHTREE SCHN 30 1.0L
Southern Glazer's Wine & Spirits of FL,000332775,BAILEYS IRISH CREAM 34 1.0L
Southern Glazer's Wine & Spirits of FL,000330395,CLICQUOT YELLOW LABEL PAD(36) 750ML
Southern Glazer's Wine & Spirits of FL,000284690,MIDORI MELON LIQ 40 1.0L
Southern Glazer's Wine & Spirits of FL,000600501,SMIRNOFF VOD GREEN APPLE 60 1.0L
Southern Glazer's Wine & Spirits of FL,000603177,SMIRNOFF VOD RASPBERRY 60 1.0L
Southern Glazer's Wine & Spirits of FL,000534577,BACARDI CKTL(RUM/BAH/PIN)CAN4/6PAD 355ML
Southern Glazer's Wine & Spirits of FL,000618985,CROWN ROYAL BLACKBERRY 70 750ML
Southern Glazer's Wine & Spirits of FL,000157604,DEKUYPER CURACAO BLUE 48 1.0L
Southern Glazer's Wine & Spirits of FL,000024672,JOHNNIE WALKER BLACK 80 BAR 1.0L
Southern Glazer's Wine & Spirits of FL,000530397,KNOB CREEK BBN 100 1.0L
Southern Glazer's Wine & Spirits of FL,000615818,MARTINI-ROSSI VERMOUTH EXTRA DRY 1.0L
Southern Glazer's Wine & Spirits of FL,000603184,SMIRNOFF VOD VANILLA 60 1.0L
Southern Glazer's Wine & Spirits of FL,000637122,TANQUERAY GIN 94.6 1.0L
Southern Glazer's Wine & Spirits of FL,000991348,GRAND MARNIER 80 1.0L
Southern Glazer's Wine & Spirits of FL,000976180,ANGOSTURA BITTERS ORANGE 6.7Z
Southern Glazer's Wine & Spirits of FL,000109101,PATRON TEQ SILVER 80 BAR 750ML
Southern Glazer's Wine & Spirits of FL,000973347,DON JULIO TEQ ANEJO 80 NAKED 750ML
Southern Glazer's Wine & Spirits of FL,000912425,GAMBINO CUVEE BRUT 750ML
Southern Glazer's Wine & Spirits of FL,000975058,JOSH CELLARS CABERNET SAUVIGNON 750ML
Southern Glazer's Wine & Spirits of FL,000570868,PRISONER RED BLEND 21 750ML
Southern Glazer's Wine & Spirits of FL,000370635,SMIRNOFF VOD BLUEBERRY 70 1.0L
Southern Glazer's Wine & Spirits of FL,000175921,ST GERMAIN LIQUEUR 40 750ML
Southern Glazer's Wine & Spirits of FL,000245835,TRES GEN TEQ REPOSADO 80 750ML
Southern Glazer's Wine & Spirits of FL,000603175,SMIRNOFF VOD CITRUS 60 1.0L
Southern Glazer's Wine & Spirits of FL,000907028,BENTLEYS BLUE CURACAO 30 1.0L
Southern Glazer's Wine & Spirits of FL,000024602,JAMESON IRISH WHISKEY 80 750ML
Southern Glazer's Wine & Spirits of FL,000091289,DAILYS LIME JUICE 1.0L
Southern Glazer's Wine & Spirits of FL,000631498,CROWN ROYAL CANADIAN 80(BAR) 1.0L
Southern Glazer's Wine & Spirits of FL,000972007,ZING ZANG BLOODY MARY MIX PET 32Z
Southern Glazer's Wine & Spirits of FL,000603441,PRISONER RED BLEND 22 750ML
Southern Glazer's Wine & Spirits of FL,000303505,DAILYS BLOODY MARY MGHTY SPICE PET 1.0L
Southern Glazer's Wine & Spirits of FL,000631461,CROWN ROYAL REGAL APPLE 70 BAR 1.0L
Southern Glazer's Wine & Spirits of FL,000163874,MIDORI MELON LIQ 40 750ML
Southern Glazer's Wine & Spirits of FL,000430016,ANCHO REYES ANCHO CHILE LIQ 80 750ML
Southern Glazer's Wine & Spirits of FL,000417378,ANGOSTURA AMARO DI ANGOSTURA 70 750ML
Southern Glazer's Wine & Spirits of FL,000537567,CRUZAN RUM AGED DARK 80 PET 1.0L
Southern Glazer's Wine & Spirits of FL,000989432,LUXARDO AMARETTO DI SASCHIRA 48 750ML
Southern Glazer's Wine & Spirits of FL,000443649,BULLEIT 95 RYE 90 1.0L
Southern Glazer's Wine & Spirits of FL,000631475,CROWN ROYAL PEACH 70(BAR) 1.0L
Southern Glazer's Wine & Spirits of FL,000616120,SMIRNOFF VOD WATERMELON 60 1.0L
Southern Glazer's Wine & Spirits of FL,000561326,SUTTER HOME CHARDONNAY(SC) 750ML
Southern Glazer's Wine & Spirits of FL,000666380,SVEDKA VOD PEACH 70 1.0L
Southern Glazer's Wine & Spirits of FL,000597191,CAPT MORGAN RUM SP MV 70 1.0L
Southern Glazer's Wine & Spirits of FL,000041175,CLICQUOT YELLOW LABEL BRUT 750ML
Southern Glazer's Wine & Spirits of FL,000948537,JIM BEAM KENTUCKY FIRE 65 1.0L
Southern Glazer's Wine & Spirits of FL,000630909,CHT STE MICH MERLOT 21 750ML
Southern Glazer's Wine & Spirits of FL,000614250,DON JULIO TEQ BLANCO 80 1.0L
Southern Glazer's Wine & Spirits of FL,000058243,CINZANO VERMOUTH ROSSO(SWEET) 1.0L
Southern Glazer's Wine & Spirits of FL,000093165,KAHLUA 40 1.0L
Southern Glazer's Wine & Spirits of FL,000047917,DAILYS SWEET - SOUR MIX RTU 1.0L
Southern Glazer's Wine & Spirits of FL,000948644,GAMBINO SPARKING WINE BRUT(SC) 750ML
Southern Glazer's Wine & Spirits of FL,000920435,GOSLINGS STORMY GING BEER 4/6P 12Z
Southern Glazer's Wine & Spirits of FL,000320481,TRES AGAVES BLOODY MARIA MIX 1.0L
Southern Glazer's Wine & Spirits of FL,000271549,TRES AGAVES MARGARITA MIX(ORG) 1.0L
Southern Glazer's Wine & Spirits of FL,000033451,MALIBU RUM COCONUT 42 1.0L
Southern Glazer's Wine & Spirits of FL,000942495,SUTTER HOME CABERNET SAUVIGNON(SC) 750ML
Southern Glazer's Wine & Spirits of FL,000513862,SUTTER HOME MOSCATO(SC) 750ML
Southern Glazer's Wine & Spirits of FL,000995661,SUTTER HOME PINOT GRIGIO(SC) 750ML
Southern Glazer's Wine & Spirits of FL,000995667,SUTTER HOME SAUVIGNON BLANC(SC) 750ML
Southern Glazer's Wine & Spirits of FL,000986379,SAUZA HACIENDA TEQ SILVER 80 1.0L
Southern Glazer's Wine & Spirits of FL,000545410,TITOS HANDMADE VODKA 25TH ANNIV 80 1.0L
Southern Glazer's Wine & Spirits of FL,000446128,CASAMIGOS TEQUILA BLANCO 80 1.0L
Southern Glazer's Wine & Spirits of FL,000446127,CASAMIGOS TEQUILA REPOSADO 80 1.0L
Southern Glazer's Wine & Spirits of FL,000011291,BOMBAY SAPPHIRE GIN 94 1.0L
Southern Glazer's Wine & Spirits of FL,000971835,DON JULIO TEQ BLANCO 80 750ML
Southern Glazer's Wine & Spirits of FL,000971837,DON JULIO TEQ REPOSADO 80 750ML
Southern Glazer's Wine & Spirits of FL,000118695,PATRON TEQUILA SILVER 80 BAR 750ML
Southern Glazer's Wine & Spirits of FL,000970726,BACARDI CKTL RUM PUNCH 11.8 CAN6/4 355ML
Southern Glazer's Wine & Spirits of FL,000390982,SMIRNOFF VODKA 80 1.0L
Southern Glazer's Wine & Spirits of FL,000036126,KETEL ONE VODKA 80 1.0L
Southern Glazer's Wine & Spirits of FL,000352429,BULLEIT BOURBON 90 1.0L
Southern Glazer's Wine & Spirits of FL,000091282,DAILYS GRENADINE SYRUP 1.0L
Southern Glazer's Wine & Spirits of FL,000019307,DEWARS WHITE LABEL 80 1.0L
Southern Glazer's Wine & Spirits of FL,000975690,JIM BEAM BOURBON 80 1.0L
Southern Glazer's Wine & Spirits of FL,000022726,JOHNNIE WALKER BLACK 80 YRC 1.0L
Southern Glazer's Wine & Spirits of FL,000009998,MAKERS MARK BOURBON 90 1.0L
Southern Glazer's Wine & Spirits of FL,000621260,SMIRNOFF VOD PEACH 60 750ML
Southern Glazer's Wine & Spirits of FL,000639479,RUFFINO PROSECCO LUMINA(SC)8/3PK 187ML
Southern Glazer's Wine & Spirits of FL,000993969,MEIOMI PINOT NOIR CALIF(SC) 750ML
Southern Glazer's Wine & Spirits of FL,000412038,CROWN ROYAL CANADIAN 80(BAR) 1.0L
Southern Glazer's Wine & Spirits of FL,000442533,MARTINI-ROSSI VERMOUTH ROSSO 1.0L
Southern Glazer's Wine & Spirits of FL,000015501,GLENLIVET SCO SM 12YR 80 1.0L
Southern Glazer's Wine & Spirits of FL,0,Summary Level Adjustments
Southern Glazer's Wine & Spirits of FL,000312315,CANADIAN CLUB 1858 80 1.0L
Southern Glazer's Wine & Spirits of FL,000020965,OBAN SCO SMALT 14YR 86 YRC 750ML
Southern Glazer's Wine & Spirits of FL,000000328,PATRON TEQ SILVER 80 750ML
Southern Glazer's Wine & Spirits of FL,000033497,DEKUYPER TRIPLE SEC 30 1.0L
Southern Glazer's Wine & Spirits of FL,000046599,TITOS HANDMADE VODKA 80 1.0L
Southern Glazer's Wine & Spirits of FL,000578234,CLASE AZUL TEQ PLATA 80 750ML
Southern Glazer's Wine & Spirits of FL,000024601,JAMESON IRISH WHISKEY 80 1.0L
Southern Glazer's Wine & Spirits of FL,000564443,ILEGAL MEZCAL JOVEN 80 1.0L
Southern Glazer's Wine & Spirits of FL,000604134,LA CREMA CHARD SONOMA CST 22 750ML
Southern Glazer's Wine & Spirits of FL,000905949,RUFFINO PROSECCO(SC)8/3PK 187ML
Southern Glazer's Wine & Spirits of FL,000529073,SKREWBALL WSKY PEANUT BUTTER 70 1.0L
Southern Glazer's Wine & Spirits of FL,000036127,KETEL ONE VODKA 80 750ML
Southern Glazer's Wine & Spirits of FL,000577924,KAMORA COFFEE LIQ 40 1.0L
Southern Glazer's Wine & Spirits of FL,000623573,SMIRNOFF VOD BLUEBERRY 60 1.0L
Southern Glazer's Wine & Spirits of FL,000603439,RUFFINO PROSECCO LUMINA(SC)LSE 187ML
Southern Glazer's Wine & Spirits of FL,000915360,JOSH CELLARS CAB SAUV CRAFTSMAN 750ML
Southern Glazer's Wine & Spirits of FL,000404725,ANGELS ENVY BBN 86.6 750ML
Southern Glazer's Wine & Spirits of FL,000028728,BACARDI RUM SUPERIOR WHITE 80 1.0L
Southern Glazer's Wine & Spirits of FL,000563699,CLASE AZUL TEQ REPOSADO 80 750ML
Southern Glazer's Wine & Spirits of FL,000017098,GREY GOOSE VODKA 80 1.0L
Southern Glazer's Wine & Spirits of FL,000014580,KIM CRAWFORD SAUV BLANC(SC) 750ML
Southern Glazer's Wine & Spirits of FL,000904165,CASAMIGOS MEZCAL JOVEN 80 1.0L
Southern Glazer's Wine & Spirits of FL,000930569,CROWN ROYAL PEACH 70 750ML
Southern Glazer's Wine & Spirits of FL,000376875,SMIRNOFF VODKA 80 12/10PK PET 50ML
"""


def normalize_sku(sku, vendor_name):
    """Normalize SKU - remove leading zeros for Southern Glazier's"""
    sku = str(sku).strip()
    if 'Southern Glazer' in vendor_name:
        # Remove leading zeros but keep at least 1 digit
        sku = sku.lstrip('0') or '0'
    return sku


def should_skip(description):
    """Check if item should be skipped"""
    desc_upper = description.upper()
    for pattern in SKIP_PATTERNS:
        if pattern in desc_upper:
            return True
    return False


def main():
    # Connect to inventory DB
    inv_conn = psycopg2.connect(**INVENTORY_DB)
    inv_cursor = inv_conn.cursor(cursor_factory=RealDictCursor)

    # Get existing vendor items
    inv_cursor.execute("""
        SELECT vi.vendor_sku, v.id as vendor_id, v.name as vendor_name
        FROM vendor_items vi
        JOIN vendors v ON v.id = vi.vendor_id
    """)
    existing = {}
    for row in inv_cursor.fetchall():
        if row['vendor_sku']:
            key = (row['vendor_id'], row['vendor_sku'])
            existing[key] = row

    # Parse CSV
    reader = csv.DictReader(io.StringIO(CSV_DATA))

    items_to_add = []
    existing_items = []
    skipped_items = []
    unknown_vendor = []

    seen = set()  # Track duplicates in CSV

    for row in reader:
        vendor_name = row['Distributor Name'].strip()
        sku = row['Distributor Item Number'].strip()
        description = row['Product Description'].strip()

        # Skip items
        if should_skip(description):
            skipped_items.append((vendor_name, sku, description))
            continue

        # Skip invalid SKUs
        if not sku or sku in ('0', '00', '000', '0000', '00000'):
            skipped_items.append((vendor_name, sku, description))
            continue

        # Get vendor ID
        vendor_id = VENDOR_MAPPING.get(vendor_name)
        if not vendor_id:
            unknown_vendor.append((vendor_name, sku, description))
            continue

        # Normalize SKU
        norm_sku = normalize_sku(sku, vendor_name)

        # Skip duplicates in CSV
        key = (vendor_id, norm_sku)
        if key in seen:
            continue
        seen.add(key)

        # Check if exists
        # Try both original and normalized SKU
        if (vendor_id, sku) in existing or (vendor_id, norm_sku) in existing:
            existing_items.append((vendor_name, sku, description))
        else:
            items_to_add.append({
                'vendor_id': vendor_id,
                'vendor_name': vendor_name,
                'sku': norm_sku,
                'original_sku': sku,
                'description': description
            })

    # Print results
    print("=" * 80)
    print("PRODUCT CATALOG ANALYSIS")
    print("=" * 80)

    print(f"\n### SUMMARY ###")
    print(f"  Already in inventory: {len(existing_items)}")
    print(f"  NEW items to add:     {len(items_to_add)}")
    print(f"  Skipped (misc/empty): {len(skipped_items)}")
    print(f"  Unknown vendor:       {len(unknown_vendor)}")

    print(f"\n### NEW ITEMS TO ADD ({len(items_to_add)}) ###")
    print("-" * 80)

    by_vendor = {}
    for item in items_to_add:
        vname = item['vendor_name']
        if vname not in by_vendor:
            by_vendor[vname] = []
        by_vendor[vname].append(item)

    for vendor_name, items in sorted(by_vendor.items()):
        print(f"\n{vendor_name} ({len(items)} items):")
        for item in items:
            print(f"  [{item['sku']}] {item['description']}")

    if unknown_vendor:
        print(f"\n### UNKNOWN VENDOR ({len(unknown_vendor)}) ###")
        for vname, sku, desc in unknown_vendor:
            print(f"  {vname}: [{sku}] {desc}")

    inv_cursor.close()
    inv_conn.close()

    return items_to_add


if __name__ == '__main__':
    main()
