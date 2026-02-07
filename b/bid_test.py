from clients_ads import perf_token, update_campaign_product_bids

token = perf_token()

campaign_id = "19295547"
sku = "2878122582"

# если bid у тебя в микрорублях (как 15000000), то 15 ₽ = 15000000
bid = "15000000"

resp = update_campaign_product_bids(
    token,
    campaign_id,
    bids=[{"sku": sku, "bid": bid}],
)

print(resp)
print("OK")
