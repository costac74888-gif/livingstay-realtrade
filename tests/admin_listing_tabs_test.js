const fs = require("fs");

const source = fs.readFileSync("static/admin.html", "utf8");

function expect(condition, message) {
  if (!condition) {
    console.error(`FAIL ${message}`);
    process.exit(1);
  }
}

expect(
  !source.includes('data-sub="listings">매물</button>'),
  "중복된 매물 서브탭이 남아 있습니다."
);
expect(
  source.includes('let listingsSubTab = "listing_requests";'),
  "매물의뢰가 기본 서브탭이 아닙니다."
);
expect(
  source.includes('data-sub="listing_requests">매물의뢰</button>') &&
    source.includes('data-sub="buy_requests">매수의뢰</button>'),
  "매물의뢰·매수의뢰 서브탭이 유지되지 않았습니다."
);
expect(
  source.includes('data-mode="direct">직거래</button>') &&
    source.includes('data-mode="broker">중개</button>'),
  "매물의뢰의 직거래·중개 필터가 유지되지 않았습니다."
);

console.log("OK  관리자 매물관리 중복 탭 제거·매물의뢰 기본화");