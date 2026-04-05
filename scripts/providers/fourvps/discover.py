import asyncio
from api import FourVpsClient

API_TOKEN = "N9YpNKU79cfGGdKjXmH9xHnsI"

async def main():
    async with FourVpsClient(token=API_TOKEN) as client:
        dcs = await client.get_dc_list()
        print("Data centers:")
        for dc in dcs:
            print(f"ID: {dc.id}, City: {dc.city}, Name: {dc.name}")

        tariffs = await client.get_tariff_list()
        print("\nTariffs:")
        for tariff in tariffs:
            print(f"Cluster: {tariff.cluster_info.name}")
            for preset in tariff.presets:
                print(f"  Preset ID: {preset.id}, Name: {preset.name}, "
                      f"CPU: {preset.cpu_number}, RAM: {preset.ram_mib} MiB, Disk: {preset.rom} GB")

if __name__ == "__main__":
    asyncio.run(main())
