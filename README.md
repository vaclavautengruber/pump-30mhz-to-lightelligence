# Pumping sensor readings from 30MHz Zensie to OSRAM Lightelligence

## Introduction

This code is an attempt to combine [30MHz Zensie API](https://api.30mhz.com/api/swagger) with [OSRAM Lightelligence API](https://api.lightelligence.io/v1/api-collection/).
**Caution: This is only a proof-of-concept, not a production-grade code - using it may lead to excessive service charges.**

The code is based on the following materials:

* [30MHz - How to get your data using the ZENSIE API](https://www.30mhz.com/doc/developing-with-the-zensie-api/)
* [30MHz - How to retrieve sensor data using the API](https://www.30mhz.com/doc/how-to-retrieve-sensor-data-using-the-api/)
* [Lightelligence - Getting Started](https://lightelligence.io/docs/getting-started)

## Usage

The use of the Docker container can be divided into two stages:

1. Preparation of the Lightelligence tennant:
  * Creation of base device type and device instances (along with their certificates)
  * Creation of the mapping between the 30MHz sensors and Lightelligence device instances
2. Runtime - pumping the readings live from 30MHz Zensie to OSRAM Lightelligence.

The first step can be accomplished with the following command (assuming that the `mapping.json` is empty and that the environment variables `LIGHTELLIGENCE_TOKEN`, `ZENSIE_API_KEY` and `ZENSIE_ORGANIZATION` are already set):

    docker run -it --rm -e LIGHTELLIGENCE_TOKEN=$LIGHTELLIGENCE_TOKEN -e ZENSIE_API_KEY=$ZENSIE_API_KEY -e ZENSIE_ORGANIZATION=$ZENSIE_ORGANIZATION -v $PWD/mapping.json:/mapping.json pump

The second step can be accomplished with the following command (it uses the `mapping.json` file generated in the previous step and assumes the environment variable `ZENSIE_API_KEY` is already set):

    docker run -d --restart=always -e ZENSIE_API_KEY=$ZENSIE_API_KEY -v $PWD/mapping.json:/mapping.json pump
