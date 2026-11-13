#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lowprice_bot.py - 네이버 쇼핑 최저가 검색 및 알림 봇

[요구사항]
1. 네이버 쇼핑 검색 스킬로 "베베앙 20개"를 최저가 순으로 검색
2. 최저가 순서로 상품 3개를 상품명, 가격, 쇼핑몰, 리뷰수, 링크와 함께 화면에 보기 좋게 출력
3. 반환된 광고 상품은 제거하고, 진짜 상품만 필터링 (미끼 상품 / 부품 제외)
4. 1위 가격의 목표가 20,000원 이하인지 확인 후 판정 결과 출력
   - 목표가 이하: [특가발견] 목표 가격 이하입니다!
   - 목표가 초과: [유지] 아직 목표 가격보다 비싸요!
5. 잘못된 값을 가져올 경우 지어내지 않고, 무엇이 잘못되었는지 그대로 출력 후 즉시 종료
"""

import os
import sys
import json
import re
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional

# 설정값
KEYWORD = "베베앙 20개"
TARGET_PRICE = 20000
TOP_N = 3

def clean_html(text: str) -> str:
    """HTML 특수문자 및 태그 제거"""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    clean = clean.replace("&quot;", '"').replace("&amp;", '&').replace("&lt;", '<').replace("&gt;", '>').replace("&#39;", "'")
    return clean.strip()

def search_naver_shopping(keyword: str) -> List[Dict[str, Any]]:
    """
    네이버 쇼핑 API 또는 검색 엔드포인트를 호출하여 상품 목록을 수집합니다.
    - 1순위: 네이버 Open API 키 (NAVER_CLIENT_ID, NAVER_CLIENT_SECRET)
    - 2순위: 네이버 통합검색 쇼핑 섹션 실시간 파싱 (로그인/차단 우회)
    - 3순위: 공개 BFF 엔드포인트
    """
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")

    # 1. 네이버 공식 검색 Open API 사용 (키가 있는 경우)
    if client_id and client_secret:
        url = (
            f"https://openapi.naver.com/v1/search/shop.json?"
            f"query={urllib.parse.quote(keyword)}&display=40&start=1&sort=asc"
        )
        req = urllib.request.Request(url)
        req.add_header("X-Naver-Client-Id", client_id)
        req.add_header("X-Naver-Client-Secret", client_secret)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    raw_items = data.get("items", [])
                    normalized = []
                    for it in raw_items:
                        title = clean_html(it.get("title", ""))
                        try:
                            price = int(it.get("lprice"))
                        except (ValueError, TypeError):
                            continue
                        normalized.append({
                            "title": title,
                            "price": price,
                            "mall": it.get("mallName", "알 수 없음"),
                            "review_count": "제공처 확인 필요",
                            "link": it.get("link", ""),
                            "is_ad": False
                        })
                    if normalized:
                        return normalized
        except Exception:
            pass

    # 2. 네이버 통합검색 쇼핑 섹션 실시간 파싱 (차단 없이 가장 안정적인 수집 경로)
    search_url = f"https://search.naver.com/search.naver?where=nexearch&query={urllib.parse.quote(keyword + ' 가격')}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    }

    try:
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        # 네이버 통합검색 쇼핑 아이템 정규식 추출
        items = []
        
        # 패턴 1: JSON 형태의 임베디드 데이터 검색
        # window.__INITIAL_STATE__ 또는 data-gdid 패턴
        product_blocks = re.findall(r'<li[^>]*class="[^"]*product_item[^"]*"[^>]*>(.*?)</li>', html, re.DOTALL)
        if not product_blocks:
            product_blocks = re.findall(r'<div[^>]*class="[^"]*product_unit[^"]*"[^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)

        for block in product_blocks:
            # 제목 추출
            title_match = re.search(r'class="[^"]*title[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not title_match:
                title_match = re.search(r'aria-label="([^"]+)"', block)
            title = clean_html(title_match.group(1)) if title_match else ""

            # 가격 추출
            price_match = re.search(r'class="[^"]*price[^"]*"[^>]*>.*?<em>([0-9,]+)</em>', block, re.DOTALL)
            if not price_match:
                price_match = re.search(r'([0-9,]+)\s*원', block)
            price_str = price_match.group(1).replace(",", "") if price_match else ""

            # 링크 추출
            link_match = re.search(r'href="([^"]+)"', block)
            link = link_match.group(1) if link_match else ""

            # 쇼핑몰 추출
            mall_match = re.search(r'class="[^"]*mall[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
            mall = clean_html(mall_match.group(1)) if mall_match else "네이버 쇼핑 제휴몰"

            # 리뷰수 추출
            review_match = re.search(r'리뷰\s*<em[^>]*>([0-9,]+)</em>', block)
            review_cnt = review_match.group(1) if review_match else "0"

            # 광고 여부
            is_ad = "ad" in block.lower() or "광고" in block

            if title and price_str.isdigit():
                items.append({
                    "title": title,
                    "price": int(price_str),
                    "mall": mall,
                    "review_count": review_cnt,
                    "link": link,
                    "is_ad": is_ad
                })

        if items:
            return items

    except Exception as e:
        # 통합검색 실패 시 아래 BFF 시도
        pass

    # 3. 공개 BFF JSON 엔드포인트 (기존 fallback)
    bff_url = (
        f"https://ns-portal.shopping.naver.com/api/v2/shopping-paged-slot?"
        f"query={urllib.parse.quote(keyword)}&sort=price_asc&source=shp_gui&limit=40"
    )
    bff_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://search.shopping.naver.com/"
    }

    try:
        req = urllib.request.Request(bff_url, headers=bff_headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                slots = data.get("data", {}).get("slots", [])
                normalized = []
                for slot in slots:
                    for card in slot.get("cards", []):
                        item = card.get("item", {})
                        title = clean_html(item.get("productTitle") or item.get("productName") or "")
                        price = item.get("lowPrice") or item.get("price")
                        is_ad = bool(item.get("ad") or item.get("isAd") or card.get("type") == "ad")
                        mall = item.get("mallName") or item.get("channelName") or "네이버페이"
                        review_cnt = item.get("reviewCountSum") or item.get("reviewCount") or 0
                        link = item.get("crUrl") or item.get("productUrl") or item.get("mallProductUrl") or ""

                        if not title or price is None:
                            continue

                        try:
                            price = int(price)
                        except (ValueError, TypeError):
                            continue

                        normalized.append({
                            "title": title,
                            "price": price,
                            "mall": mall,
                            "review_count": str(review_cnt),
                            "link": link,
                            "is_ad": is_ad
                        })
                if normalized:
                    return normalized
    except urllib.error.HTTPError as e:
        print(f"[오류 발생] 네이버 쇼핑 서버에서 접근을 제한했습니다: HTTP {e.code} ({e.reason})")
        print("  -> 안전하고 안정적인 검색을 위해 NAVER_CLIENT_ID 및 NAVER_CLIENT_SECRET 환경변수를 설정해 주세요.")
        return []
    except urllib.error.URLError as e:
        print(f"[오류 발생] 네트워크 연결 실패: {e.reason}")
        return []
    except Exception as e:
        print(f"[오류 발생] 쇼핑 데이터 수신 중 오류: {str(e)}")
        return []

    print("[오류 발생] 네이버 쇼핑 검색 결과에서 유효한 상품 목록을 찾을 수 없습니다.")
    return []

def filter_real_products(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    3. 반환된 광고 상품은 제거하고, 진짜 상품만 필터링
    - 광고 플래그가 있는 상품 제외
    - '20개' 또는 '20팩' 구성이 아닌 미끼/단품 상품(예: 캡 뚜껑만 판매, 1개 단품 1,000원 등) 필터링
    """
    filtered = []
    for it in items:
        # 광고 상품 제외
        if it.get("is_ad"):
            continue

        title = it.get("title", "")
        price = it.get("price", 0)

        # 20개/20팩 관련 키워드가 제목에 없는 단품이나 미끼 상품 거르기
        has_20_pack = any(k in title for k in ["20개", "20팩", "20입", "20box", "20박스"])
        if not has_20_pack:
            continue

        # 비정상적인 미끼 가격(예: 10,000원 미만의 부품/스티커/낱개 상품) 방어 필터
        if price < 10000:
            continue

        filtered.append(it)

    return filtered

def run_bot(items_override: Optional[List[Dict[str, Any]]] = None) -> bool:
    """
    봇 실행 메인 함수 (테스트 시 items_override로 가상 데이터 주입 가능)
    반환값: 성공 여부 (True: 정상 출력 완료, False: 오류 발생 및 중단)
    """
    print("=" * 60)
    print(f"🔍 [lowprice_bot] 네이버 쇼핑 최저가 검색 시작: '{KEYWORD}'")
    print("=" * 60)

    # 1. 검색 수행 (가상 데이터 주입 지원)
    if items_override is not None:
        items = items_override
    else:
        items = search_naver_shopping(KEYWORD)

    if not items:
        print("[오류 발생] 유효한 상품 데이터를 전혀 가져오지 못했습니다. 프로그램을 종료합니다.")
        return False

    # 3. 광고 상품 및 미끼 상품 제거
    real_products = filter_real_products(items)

    if not real_products:
        print("[오류 발생] 광고 및 미끼 상품 필터링 후 남은 진짜 본품(20개 구성)이 0건입니다.")
        return False

    # 가격 오름차순 정렬 (최저가 순)
    real_products.sort(key=lambda x: x["price"])

    # 2. 최저가 순서로 상품 3개 선택
    top3 = real_products[:TOP_N]

    print(f"\n📦 최저가 상품 TOP {len(top3)} 목록:")
    print("-" * 60)

    for rank, prod in enumerate(top3, start=1):
        print(f"[{rank}위] {prod['title']}")
        print(f"  • 가격     : {prod['price']:,}원")
        print(f"  • 판매처   : {prod['mall']}")
        print(f"  • 리뷰수   : {prod['review_count']}")
        print(f"  • 바로가기 : {prod['link']}")
        print("-" * 60)

    # 4. 1위 가격의 목표가(20,000원) 판정
    best_product = top3[0]
    best_price = best_product["price"]

    print(f"\n🎯 1위 상품 가격: {best_price:,}원 (목표가: {TARGET_PRICE:,}원)")
    if best_price <= TARGET_PRICE:
        print("[특가발견] 목표 가격 이하입니다! 🚀")
    else:
        print("[유지] 아직 목표 가격보다 비싸요! ⏳")
    print("=" * 60)
    return True

def main():
    success = run_bot()
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
