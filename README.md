![Alt text](assets/eurostat.png "Title")
image source: *https://ec.europa.eu/eurostat*

# Eurostat downloader QGIS plugin

It can be used to add Eurostat datasets as tables in QGIS and join them with vector layers.

# External dependencies

In order for this plugin to run properly, the [eurostat python package](https://pypi.org/project/eurostat/) needs to be installed. It is available via PyPi.

## Installing dependencies on Linux and Windows

Users of these two platforms are not required to do anything. The external dependencies are already provided inside the plugin folder. If issues appear regarding plugin dependencies, please contact me and let me know.

## Installing dependencies on macOS

For macOS users, check tutorials online on how to handle the installation of external python packages. The [eurostat python package](https://pypi.org/project/eurostat/) needs to be installed.

- https://gis.stackexchange.com/questions/351280/installing-python-modules-for-qgis-3-on-mac
- https://gis.stackexchange.com/questions/419975/pip-install-inside-qgis-fails

# How to install the plugin

Navigate [here](https://github.com/alecsandrei/eurostat_downloader/releases) and download the zip file associated with the latest release (eurostat_downloader.zip). After that, in QGIS, go to Plugins -> Manage and Install Plugins -> Install from zip and select the downloaded zip file.

The plugin is also available in the [QGIS plugin repository](https://plugins.qgis.org/plugins/eurostat_downloader/). It is currently flagged as an experimental plugin, so you will have enable the *Show also experimental* plugins setting in order to download it from within QGIS.

# How to use the plugin

## Selecting a dataset from the Eurostat database

Let's start by downloading a vector layer from [here](https://ec.europa.eu/eurostat/web/gisco/geodata/reference-data/administrative-units-statistical-units/countries). I will choose [this](https://gisco-services.ec.europa.eu/distribution/v2/countries/download/ref-countries-2020-60m.shp.zip) one and add it to QGIS.

Open the plugin and type anything in the search bar. The table of contents will be generated. This may take a while, depending on how fast your internet speed is. Search for any dataset that you would like to use. I will choose **CENS_HNCTZ: Population by sex, age and citizenship**. Click on it, and wait for the table to fill.

![Alt text](assets/how_to_use_the_plugin_1.png "Title")

## Applying filters to the dataset

Now that the table is filled with data, we can apply filters to it. In order to do so, left click on the name of the column. I will select the **T** value (which stands for total) from the 3 available in the sex column.

![Alt text](assets/how_to_use_the_plugin_2.png "Title")

We can see the table also filtered dynamically as we selected the **T** value. There is a problem though. If we click on the **citizen** column we will see very abstract abbreviations like FOR, NAT, STLS, and UNK. In the previous example it was easy to guess that F, M AND T stand for female, male and total. In this example, we will need some sort of translation to describe what the abbreviation stands for. To do this, close the **Edit section** window and select a language from the bottom left. Now click on the **citizen** column again.

![Alt text](assets/how_to_use_the_plugin_3.png "Title")

The time range can also be filtered.

## Adding the table and joining the data with a vector layer

Now that we applied the filters, if we just want to export the table for further analysis in Excel, Python or R we can click on the **Add table** button. A temporary table will be created in your QGIS instance and you are free to export the data.

We can also join the data to the vector layer we downloaded earlier. By default, the plugin tries to infer both the column with the geographic codes from the Eurostat dataset and the field from the vector layer that matches the values from that Eurostat dataset column. In my case, the plugin selected FID for the layer join field and geo for the table (Eurostat data) join field by default. Make sure to check if the join fields were correctly selected. Now, we can just join the data by clicking on the **Join data** button. **Be careful!** The joined data is temporary. You will now need to export the vector layer in order to keep the joined data.

![Alt text](assets/how_to_use_the_plugin_4.png "Title")
