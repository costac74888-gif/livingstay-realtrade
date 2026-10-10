from hs2_design.domain import ContractError


def mobile_shell(html):
    """Only presentation changes; source shell/controller/API remain shared."""
    marker='<body class="supermap-page">'
    if html.count(marker)!=1 or 'id="listingList"' not in html or 'id="mapCanvas"' not in html:
        raise ContractError("SHARED_SEARCH_SHELL_REQUIRED")
    return html.replace(marker,'<body class="supermap-page" data-mobile-experience="true" data-mobile-view="list">',1).replace("</head>",
        '<link rel="stylesheet" href="/hs2/search/assets/mobile.css">\n<script src="/hs2/search/assets/mobile.js" defer></script>\n</head>',1)
