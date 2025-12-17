What's New

🕐 5 min read

VizQL Data Service 2025.3
October 2025

In this release, VizQL Data Service (VDS) has the following enhancements:

View updated metadata: The Request data source metadata method now returns groups, bins, and parameters. You can also see the column class and calculation formulas. For more information, see the Example output section in Request Data Source Metadata.

Query existing bins: You can now query bins and view the result. For more information, see the Parameters with bins example in Query a Data Source.

Override existing parameters: You can now override the values currently persisted on the published data source. For more information, see the Calculated field with a parameter example in Query a Data Source.

Query new bins on the fly: You can now create a new bin that does not already exist on the published data source. For more information, see the Create a new bin section in Creating Queries.

Query using fieldName instead of fieldCaption: VDS now supports passing the fieldName in its methods. This allows renamed fields to be resolved correctly, preventing query failures. For more information, see the interpretFieldCaptionsAsFieldNames option in either the Request data source metadata, Request data source model or Query data source methods.

Expose type for all fields and formulas for calculations: VDS now returns the current read metadata return value for a field to include parameters for columnClass, and formula. For more information, see the Request data source metadata response section in Request Data Source Metadata.

Query table calculations: VDS supports everything you see in the quick table calculations, as well as custom table calculations and nested table calculations. For more information, see the Table Calculations section.

See the data source model: You can now see the logical table and relationship metadata in a published data source. For more information, see Get Data Source Model.

VizQL Data Service 2025.2
June 2025

This release has three enhancements: multiple credentials support, updates to the schema, and a Python client library.

Support for multiple credentials
The VizQL Data Service now supports multiple credentials. For more information, see Data sources that require multiple credentials.

Schema update
We updated the OpenAPI schema. The most significant change is that the Request data source metadata method now returns defaultAggregation. For more information, see the API documentation and the OpenAPI schema.

VizQL Data Service Python SDK
The VizQL Data Service Python SDK is a lightweight client library that enables interaction with Tableau’s VizQL Data Service APIs. It supports both Tableau Cloud and Tableau Server deployments and offers both synchronous and asynchronous methods for querying the APIs. For more information, see the VizQL Data Service Python SDK GitHub repo.

VizQL Data Service 2025.1
February 2025

This is the initial public release of the VizQL Data Service (VDS). VDS provides a way for you to access your data outside of a Tableau visualization (viz).

With a viz, you perform operations like dragging a pill to rows or columns. This achieves two things: It fetches data from the data source, and it creates a visualization of that data. VDS allows you to perform a fetch of the data without the need for any visualization.

Changes from the earlier release
There are substantial changes from the previous developer preview release. If you used the developer preview release, note these changes:

We now refer to fields instead of columns. For more information, see the VDS API Documentation.
Our authentication process has changed to use the Tableau REST API methods. For more information, see Configuration
We now accept the data source LUID instead of the data source name, and have changed the syntax for specifying database credentials. For more information, see Connect to your data source.
Quantitative filters used to handle both numbers and dates. This has been broken out into QuantitativeNumericalFilter and QuantitativeDateFilter, which are specific to their types.
The Filter object has changed. Now each ‘Filter requires a FilterField.
By default, a Filter excludes null values. Use an includeNulls field with a quantitative filter.
We removed the SPECIAL filter type, and now a quantitative filter has new options of ONLY_NULL, and ONLY_NON_NULL, which you can use to filter appropriately.
We updated the RelativeDateFilter. The LASTN NEXTN are used with rangeN to specify relative ranges. The other date range types are shortcuts. For more information, see the Relative date filters.
We added a new MatchFilter type to do string matching.
Some function have new and improved names.
VizQL Data Service Developer Preview
October 2024

In this developer preview release, we added the API Access permission capability. To query a data source with the VizQL Data Service, you must assign this capability in the Permission dialog. For more information, see Assign API access capability in Configuration.

We also moved theVizQL Data Service Postman collection from its location in the Tableau pre-release site to its new GitHub repository.

June 2024

This is the initial developer preview release of the VizQL Data Service. This is a closed release, only available to a small number of developers.

This release introduces the initial set of API methods and endpoints for using the VizQL Data Service.
VizQL Data Service Introduction

How does it work?
Endpoints
Required tools
Availability
🕐 3 min read

The VizQL Data Service (VDS) provides a programmatic way for you to access your published data outside of a Tableau visualization. With a viz, you perform operations like dragging a pill to rows or columns. This accomplishes two things. It fetches data from the data source, and then creates a visualization of that data.

With VDS, you can fetch the data without any need for a visualization.

How does it work?
VDS is a standard HTTP service with a Query data source method and a Request data source metadata method. In both methods, you describe your data request in the request body as a JSON object.

Note: VDS only works with published data sources.
Endpoints
The endpoint for the Query data source method is:

POST https://{your-pod}.online.tableau.com/api/v1/vizql-data-service/query-datasource

The endpoint for the Request data source metadata method is:

POST https://{your-pod}.online.tableau.com/api/v1/vizql-data-service/read-metadata

Note: Your pod is in the first portion of the domain of your site URL after signing in to Tableau Cloud. For example, if your sign-in URL is https://10az.online.tableau.com, your pod is 10az.
Required tools
There are many ways to make API requests. You can create your own or use existing tools like cURL and Postman. See the VizQL Data Service Collection in the Tableau APIs Postman collection to help get you started.

Availability
VDS is available for both Tableau Cloud and Tableau Server. To use VDS with Tableau Server, you must be on Tableau Server 2025.1 or later.
Configuration

🕐 4 min read

Assign API access capability
Configure authentication
Sign in using a personal access token (PAT)
Sign in using a JSON web token (JWT)
Sign in using username and password
Find the data source LUID
Option 1: Get the LUID using Tableau Cloud or Tableau Server
Option 2: Get the LUID using the Tableau REST API
Assign API access capability
To query a data source with VizQL Data Service (VDS), you must first assign the API Access capability in the Permission dialog. For information about setting up this data source capability in the Tableau user interface, see the Permission Capabilities and Templates topic in either Tableau Cloud Help or Tableau Server Help.

For information about setting up this data source capability using the REST API, see Permissions.

Configure authentication
VDS requires that you send an authentication token with each request. The token lets Tableau Cloud or Tableau Server verify your identity and makes sure that you’re signed in. To get a token, you can call the Tableau REST API Sign In method, in one of three ways.

Sign in using a personal access token (PAT)
To sign in using a PAT, see Make a Sign In Request with a Personal Access Token in the Tableau REST API Help for more information.

Sign in using a JSON web token (JWT)
If you use a JWT, set the scope (scp) in the JWT to tableau:viz_data_service:read. The permissions of the user in the JWT determine query results.

See Make a Sign In Request with a JWT in the Tableau REST API Help for more information on using a JWT to create a credentials token that you can use with VDS.

Sign in using username and password
See Make a Sign In Request with Username and Password in the Tableau REST API Help for more information.

For information about token expiration, changing the token timeout value, and more, see Using the Authentication Token In Subsequent Calls in the Tableau REST API Help.

Find the data source LUID
To run a VDS method, you must know the locally unique identifier (LUID) of the published data source you’re requesting information about. There are two options for finding the data source LUID.

Option 1: Get the LUID using Tableau Cloud or Tableau Server
In the Tableau navigation menu, select Explore.
At the top of the Explore screen, select All Data Sources in the dropdown menu.
In the list of data sources, select the data source you want the LUID for.
On the data source page, select the Details icon (Details icon) next to the data source name.
The LUID is at the bottom of the Data Source Details screen.

Tableau Data Source Details screen with the data source LUID emphasized

Option 2: Get the LUID using the Tableau REST API
Use the Query Data Sources method to return a list of data sources on your site. This method returns the official data source name in the contentURL attribute. The associated id of the contentURL is your data source LUID.
Request Data Source Metadata

🕐 2 min read

Get the data structure in the data source
Request data source metadata response
Example responses
Get the data structure in the data source
The Request data source metadata method provides you with information about the queryable fields in a data source. This method requires that you pass in the data source object, as shown in this example:

{
    "datasource": {
        "datasourceLuid": "1a2a3b4b-5c6c-7d8d-9e0e-1f2f3a4a5b6b",
    }
}
The request has the following options:

bypassMetadataCache: Set to true if either the published data source or the underlying database has changed within your current session. When set to true, VizQL Dat Service (VDS) refreshes the metadata.
interpretFieldCaptionsAsFieldNames: When set to true, the response returns the fieldName value everywhere the fieldCaption is used. This is also true for parameters. For example, if you set this field to true, the response returns, for example, Parameter 2 instead of Profit Bin Size.
Request data source metadata response
This API method returns two objects: data and extraData. The data object returns these fields:

fieldName: The underlying field name on the data source.
fieldCaption: This is what you need to pass into a query. This is often the same as fieldName.
dataType: Either INTEGER, REAL, STRING, DATETIME, BOOLEAN, DATE, SPATIAL, or UNKNOWN.
defaultAggreation: The default aggregation applied to the field.
columnClass: The type of field. Either COLUMN, BIN, GROUP, CALCULATION, or TABLE_CALCULATION.
formula: The formula for this field if it is a calculation.
logicalTableId: If you have a data model with more than one logical table, this tells you which table the field originated from.
The extraData object returns a parameters object with these fields:

parameterType: Either ANY_VALUE (accepts any value without restrictions), LIST (a set number of values from which you can choose), QUANTITATIVE_DATE (a date range with specified minimum, maximum, and granularity settings), QUANTITATIVE_RANGE (a numeric range with specified minimum, maximum, and step values), or ALL (no restrictions).
parameterName: The internal name defined by Tableau.
parameterCaption: The user-defined name of the parameter to identify and reference the parameter.
dataType: Either INTEGER, REAL, STRING, BOOLEAN, and DATE.
value: The default value for the parameter.
min: The maximum value for the range.
max: The minimum value for the range.
step: The jumps between values.
Note:
DATETIME and SPATIAL are currently not supported parameter dataType values.
Date type parameters using range controls don't support step size validation when configured with ISO Years, ISO Quarters, or ISO Weeks (all ISO period types).
Example responses
A bin on the data source
{
    "data": [
        {
            "fieldName": "Profit (bin)",
            "fieldCaption": "Profit (bin)",
            "dataType": "INTEGER",
            "defaultAggregation": "NONE",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "BIN"
        }
    ]
}

A group on the data source
{
    "data": [
        {
            "fieldName": "Category (group)",
            "fieldCaption": "Category (group)",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "GROUP"
        }
    ]
}
A calculation on the data source
{
    "data": [
        {
            "fieldName": "Calculation_1368249927221915648",
            "fieldCaption": "Profit Ratio",
            "dataType": "REAL",
            "defaultAggregation": "AGG",
            "columnClass": "CALCULATION",
            "formula": "SUM([Profit])/SUM([Sales])"
        }
    ]
}
Full example from the Superstore data source
{
    "data": [
        {
            "fieldName": "Calculation_1890667447609004040",
            "fieldCaption": "TableCalc",
            "dataType": "REAL",
            "defaultAggregation": "AGG",
            "columnClass": "TABLE_CALCULATION",
            "formula": "RUNNING_SUM(SUM([Sales]))"
        },
        {
            "fieldName": "Category",
            "fieldCaption": "Category",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Regional Manager",
            "fieldCaption": "Regional Manager",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "People_D73023733B004CC1B3CB1ACF62F4A965",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Ship Date",
            "fieldCaption": "Ship Date",
            "dataType": "DATE",
            "defaultAggregation": "YEAR",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Sub-Category",
            "fieldCaption": "Sub-Category",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Profit (bin)",
            "fieldCaption": "Profit (bin)",
            "dataType": "INTEGER",
            "defaultAggregation": "NONE",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "BIN"
        },
        {
            "fieldName": "Segment",
            "fieldCaption": "Segment",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Sales",
            "fieldCaption": "Sales",
            "dataType": "REAL",
            "defaultAggregation": "SUM",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Ship Mode",
            "fieldCaption": "Ship Mode",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Discount",
            "fieldCaption": "Profit",
            "dataType": "REAL",
            "defaultAggregation": "SUM",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Order Date",
            "fieldCaption": "Order Date",
            "dataType": "DATE",
            "defaultAggregation": "YEAR",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Calculation_1368249927221915648",
            "fieldCaption": "Profit Ratio",
            "dataType": "REAL",
            "defaultAggregation": "AGG",
            "columnClass": "CALCULATION",
            "formula": "SUM([Profit])/SUM([Sales])"
        },
        {
            "fieldName": "Customer Name",
            "fieldCaption": "Customer Name",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Returned",
            "fieldCaption": "Returned",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Returns_2AA0FE4D737A4F63970131D0E7480A03",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Postal Code",
            "fieldCaption": "Postal Code",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Order ID",
            "fieldCaption": "Order ID",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Product Name",
            "fieldCaption": "Product Name",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Quantity",
            "fieldCaption": "Quantity",
            "dataType": "INTEGER",
            "defaultAggregation": "SUM",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "City",
            "fieldCaption": "City",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Sales (bin)",
            "fieldCaption": "Sales (bin)",
            "dataType": "INTEGER",
            "defaultAggregation": "NONE",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "BIN"
        },
        {
            "fieldName": "State/Province",
            "fieldCaption": "State/Province",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Profit",
            "fieldCaption": "Profit Caption",
            "dataType": "REAL",
            "defaultAggregation": "SUM",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Region",
            "fieldCaption": "Region",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Country/Region",
            "fieldCaption": "Country/Region",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "COLUMN"
        },
        {
            "fieldName": "Calculation_1890667447610966025",
            "fieldCaption": "Disaggregated Calc",
            "dataType": "REAL",
            "defaultAggregation": "SUM",
            "columnClass": "CALCULATION",
            "formula": "1+2.5"
        },
        {
            "fieldName": "Category (group)",
            "fieldCaption": "Category (group)",
            "dataType": "STRING",
            "defaultAggregation": "COUNT",
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "columnClass": "GROUP"
        }
    ],
    "extraData": {
        "parameters": [
            {
                "parameterType": "LIST",
                "parameterName": "Parameter 3",
                "parameterCaption": "Greeting String",
                "dataType": "STRING",
                "value": "Hello",
                "members": [
                    "Hello",
                    "Hi",
                    "Greetings",
                    "Hey"
                ]
            },
            {
                "parameterType": "QUANTITATIVE_RANGE",
                "parameterName": "Parameter 1",
                "parameterCaption": "Top Customers",
                "dataType": "INTEGER",
                "value": 5.0,
                "min": 5.0,
                "max": 20.0,
                "step": 5.0
            },
            {
                "parameterType": "QUANTITATIVE_RANGE",
                "parameterName": "Parameter 2",
                "parameterCaption": "Profit Bin Size",
                "dataType": "INTEGER",
                "value": 200.0,
                "min": 50.0,
                "max": 200.0,
                "step": 50.0
            }
        ]
    }
}
Get Data Source Model

🕐 2 min read

Get the data model in the data source
Request data source model response
Example output
Get the data model in the data source
The Request data source model method provides you with the logical table and relationship metadata in a published data source. This method requires that you pass in the data source object, as shown in this example:

{
    "datasource": {
        "datasourceLuid": "",
    }
}
Request data source model response
This API method returns two objects: logicalTables and logicalTableRelationships. The logicalTables object returns these fields:

logicalTableId: The logical table LUID.
caption: The user-defined logical table display name.
The logicalTableRelationships object returns these fields:

fromLogicalTable: Contains the key:value pair for LUID of the table on the left.
toLogicalTable: Contains the key:value pair for LUID of the table on the right.
Example output
For this example, let’s use a data source with the following model in the Tableau user interface:

Data model graph

A request to this data source returns the following response:

{
    "logicalTables": [
        {
            "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
            "caption": "Orders"
        },
        {
            "logicalTableId": "People_D73023733B004CC1B3CB1ACF62F4A965",
            "caption": "People"
        },
        {
            "logicalTableId": "Returns_2AA0FE4D737A4F63970131D0E7480A03",
            "caption": "Returns"
        }
    ],
    "logicalTableRelationships": [
        {
            "fromLogicalTable": {
                "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862"
            },
            "toLogicalTable": {
                "logicalTableId": "People_D73023733B004CC1B3CB1ACF62F4A965"
            }
        },
        {
            "fromLogicalTable": {
                "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862"
            },
            "toLogicalTable": {
                "logicalTableId": "Returns_2AA0FE4D737A4F63970131D0E7480A03"
            }
        }
    ]
}
For more information, see The Tableau Data Model.
Query a Data Source

🕐 11 min read

Anatomy of a query
The data source object
The query object
The options object
Return format
OBJECTS return vs. ARRAYS return option
Date formats
Anatomy of a query
The JavaScript Object Notation (JSON) request body for the Query data source method has three components.

datasource: Required. This is an object that tells you which data source to query and, optionally, takes credentials.
query: Required. This is how you specify which fields you want to retrieve information from. To get the names of the fields in your data source, see Get Data Source Information.
options: Optional. Options are metadata that you can use to adjust the behavior of the query.
The following example shows the basic structure of a query.

{
"datasource": { 
    "datasourceLuid": "",
 },
"options": {
    "debug": true
},
  "query": { 
    "fields": [
       // fields here
    ]
  }
}
The data source object
The datasource object takes a datasourceLuid. To find your data source LUID, see Find the data source LUID.

{
"datasource": {
    "datasourceLuid": "",
 },
  "query": { 
    "fields": [
       // fields here
    ]
  }
Data sources that require credentials
If you have a data source that requires credentials, enter them in an additional connection object.

{
"datasource": {
    "datasourceLuid": "",
    "connections": [
        {
          "connectionLuid": "31752d0a-ec9d-11ee-9ad5-0a61dcca52fb",
          "connectionUsername": "test",
          "connectionPassword": "password"
        }
    ]
 },
  "query": { // See below for more details
    "fields": [
       // Fields here
    ]
  }
}
Note: While VDS does not support data sources that have more than one connection that requires a username and password, VDS does support data sources that have a single connection that requires authentication. Use connectionUsername and connectionPassword to provide authentication for your connection. If you only have a single connection that requires a username and password, the connectionLuid property isn't required. The connectionLuid property is only required if you must provide credentials for multiple connections.
For data sources that require non-embedded credentials, add the following fields to your connection object in the body of the request.

connectionUsername
connectionPassword
Data sources that require multiple credentials
If you have multiple connections that each require a username and password, add a list of connections. For each connection, you must provide a connectionLuid, a connectionUsername, and a connectionPassword.

To find the connectionLuid, use the Query Data Source Connections method. This method returns an ID for each connection on the specified data source. The value of your connection’s ID is the value to use for connectionLuid.

{
"datasource": {
    "datasourceLuid": "2bac64a3-e216-4d8f-891c-905f9ce33ac3",
    "connections": [
        {
          "connectionLuid": "31752d0a-ec9d-11ee-9ad5-0a61dcca52fb",
          "connectionUsername": "test",
          "connectionPassword": "password"
        },
        {
          "connectionLuid": "54ec51f6-7b1c-40d8-a55c-d4a70333c358",
          "connectionUsername": "test2",
          "connectionPassword": "password2"
        }
    ]
 },
  "query": { // See below for more details
    "fields": [
       // Fields here
    ]
  }
}
The query object
The query object contains these basic components:

fields: Required. This contains an array of fields that define the desired output of the query.
filters: Optional. This contains an array of filters to apply to the query. They can include fields that aren’t in the fields array.
parameters: Optional. Parameters enable dynamic, user-defined inputs to control and customize the results returned by the data source query. They can act as variables (like numbers, dates, booleans, or strings) that replace constant values in calculations, or they can act as filters.
Fields
You can list the fields that you want from your published data source and see the returned data. Fields can come in multiple forms: dimensions, measures, or custom calculations. Fields can also be sorted, aliased, and have their decimal places formatted (if they’re a number).

Note: The fieldCaption must be the fieldCaption returned from Request data source metadata method.
Dimensions
Pass in a fieldCaption and get the data for that field as a dimension.

The following example shows sorting, which is optional.

"fields": [
        {
            "fieldCaption": "Category",
            "sortPriority": 1
        },
        {
            "fieldCaption": "Sub-Category",
            "sortPriority": 2,
            "sortDirection": "DESC"
        },
]
Fields with aggregations or measures
You can add an aggregation, or function, to a field to treat the field as a measure.

"fields": [
        {
            "fieldCaption": "Sales",
            "function": "SUM",
            "maxDecimalPlaces": 2
        }
]
VDS supports the following functions for aggregations:

SUM
AVG
MEDIAN
COUNT
COUNTD
MIN
MAX
STDEV
VAR
COLLECT
YEAR
QUARTER
MONTH
WEEK
DAY
TRUNC_YEAR
TRUNC_QUARTER
TRUNC_MONTH
TRUNC_WEEK
TRUNC_DAY
Custom calculations
To specify a new, custom calculation as a field, give it a fieldCaption and a string in Tableau calculation syntax. To query an existing calculation, use the preceding methods to query an existing field.

"fields": [
        {
            "fieldCaption": "Profit Margin",
            "calculation": "SUM([Profit])/SUM([Sales])"
        }
]
The following is a complete list of things you can add to your field object.

fieldCaption: Required. The name of the column that must be supplied. Either a reference to a specific column in the data source or, in the case of a calculation, a user-supplied name for the calculation.
fieldAlias: Optional. An alternate name to give the column in the output. This is only used in Object format output.
function: Optional. Provide a Function for a Measure to generate an aggregation against that Field’s values. For example, providing the SUM Function will cause an aggregated SUM to be calculated for that Field. A Field cannot contain both a Function and a Calculation.
calculation: Optional. Provide a Calculation to generate a new data Field based on that Calculation. The Calculation should contain a string based on the Tableau Calculated Field Syntax. Since this is a newly generated Field, you must give it its own unique fieldCaption. A Field cannot contain both a Function and a Calculation.
maxDecimalPlaces: Optional. The maximum number of decimal places in the returned value. Any trailing 0s will be dropped. The maxDecimalPlaces value must be greater or equal to 0.
sortDirection: Optional. The direction of the sort, either ascending or descending.
sortPriority: Optional. To enable sorting on a specific Field, provide a sortPriority for that Field, and that Field will be sorted. The sortPriority provides a ranking of how to sort Fields when multiple Fields are being sorted. The highest priority (lowest number) field is sorted first. If only one field is being sorted, then any value may be used for sortPriority. The value should be an integer and can be negative.
Additional rules about fields
You must query at least one field.
You can’t query the same field twice.
You can’t have duplicate sort priorities.
Filters
You can also filter the fields you receive back from the datasource. To specify a filter, you can create a field (like above) to operate on. This field does not have to be in the list of original fields. There are different kinds of filters, each requiring a filterType and a field to filter on.

Set filters
You can include or exclude certain values from your dataset when showing results. The following filter is used for dimensions. You must set the Boolean exclude and provide a list of values to either exclude (when exclude=true) or include (when exclude=false).

"filters": [
    {
      "field": {
         "fieldCaption": "Ship Mode"
      },
      "filterType": "SET",
      "values": [ "First Class"],
      "exclude": false
    }
]
Note that the values array can’t be empty.

Quantitative filters
A quantitative filter operates on a field with an aggregation. It can specify a minimum, maximum, or range of values. It can also be used to handle both null and non-null values.

Quantitative filters must have quantitativeFilterType, which can be one of the following (with some rules):

MIN: The “min” value must be set.
MAX: The “max” value must be set.
RANGE: Both the “min” and “max” values must be set.
ONLY_NULL: Show only null values in the return data set. That is, don’t include a “min” value or a “max” value.
ONLY_NON_NULL: Show only non-null values. That is, don’t include a “min” value or a “max” value.
If you have type ONLY_NULL or ONLY_NON_NULL, you can’t have minimums and maximums specified.

If you have type MIN, MAX, or RANGE, you can also set the additional property includeNulls to true (it’s false by default) if you’d like to include nulls.

There are two types of quantitative filters, one for dates and one for numerical values.

Quantitative numerical filters
For measures, set the filterType to QUANTITATIVE_NUMERICAL.

// measure range example
"filters": [
  {
    "column": {
        "fieldCaption": "Sales",
        "function": "SUM"
    },
    "filterType": "QUANTITATIVE_NUMERICAL",
    "quantitativeFilterType": "MIN",
    "min": 10000
  }
]
Quantitative date filters
For dates, set the filterType to QUANTITATIVE_DATE.

The only difference here is that, instead of specifying min and max, you can instead specify minDate and maxDate.

// date range example
"filters": [
  {
     "field": {
         "fieldCaption": "Order Date"
      },
    "filterType": "QUANTITATIVE_DATE",
    "quantitativeFilterType": "MAX",
    "maxDate": "2020-04-01"
  }
]
Relative date filter
A relative date filter is a way to specify a range of dates from a given anchor. If you set NO anchor, today’s date will be used by default.

You must also set the variables periodType and dateRangeType.

periodType can be one of the following values:

MINUTES
HOURS
DAYS
WEEKS
MONTHS
QUARTERS
YEARS
dateRangeType can be one of the following values:

LAST
CURRENT
NEXT
LASTN (requires you to add rangeN field)
NEXTN (requires you to add rangeN field)
TODATE
See the following Tableau Filter[Order Date] screen to help understand what these dateRangeTypes mean.

Filter [Order Date] screen

LAST
LASTN
CURRENT
NEXTN
NEXT
TODATE
Some examples
// January 1st, 2020 - March 1st, 2020
"filters": [
  {
    "filterType": "DATE",
    "field": {
    	"fieldCaption": "Order Date"
     },
    "periodType": "MONTHS",
    "dateRangeType": "NEXTN",
    "rangeN": 3,
    "anchorDate": "2020-01-01"
  }
]
// January 1st, 2020 - December 31st, 2020
"filters": [
  {
    "filterType": "DATE",
    "field": {
    	"fieldCaption": "Order Date"
     },
    "periodType": "YEARS",
    "dateRangeType": "CURRENT",
    "anchorDate": "2020-01-01"
  }
]
// All dates up to today's date (no anchor defaults to today)
"filters": [
  {
    "filterType": "DATE",
     "field": {
    	"fieldCaption": "Order Date"
     },
    "periodType": "YEARS",
    "dateRangeType": "TODATE,
  }
]
Requirement: You must have a periodType and a dateRangeType. If you specify a rangeN, then your dateRangeType must be lastN or nextN.

Top N filter
You can see top or bottom values of a given field by some aggregation.

A top N filter, or filterType: TOP, allows you to find the top N results of a given category. You need to specify the following inputs:

fieldCaption: The same as other queries, this is the column on which you want to filter.
fieldToMeasure: This is a filter column on which you are finding the top or bottom results of.
direction: Either TOP or BOTTOM to show the highest or lowest results.
howMany: An integer for how many results you would like to see.
See the following example, “Top 10 States with the highest Profit”.

"filters": [
  {
    "field": {
    	"fieldCaption": "State/Province"
     },
    "filterType": "TOP",
    "howMany": 10,
    "fieldToMeasure": {
      "fieldCaption": "Profit",
      "function": "SUM"
    },
    "direction": "TOP"
  }
]
Requirement: You must have howMany and fieldToMeasure.

Match filter
You can also provide substrings to conditionally match various filter types.

"filters": [
    {
      "field": {
    	"fieldCaption": "State/Province"
      },
      "filterType": "MATCH",
      "startsWith": "A",
      "endsWith": "a",
      "contains": "o",
      "exclude": false
    }
]
Requirement: You must have at least one of startsWith, endsWith, or contains.

Context filter
You can add a context filter and create a dependent filter on a quantitative filter or a top N filter, ideally to improve performance. You can add “context” as a boolean field to any filter to make it a context filter. For more information about Tableau context filters, see Use Context Filters.

"filters": [
    {
        "field": {
    	    "fieldCaption": "SubCategory"
        },
        "filterType": "TOP",
        "howMany": 10,
        "fieldToMeasure": {
            "fieldCaption": "Sales",
            "function": "SUM"
        },
       "direction": "TOP"
    },
    {
        "field": {
    	    "fieldCaption": "Category"
        },
        "filterType": "SET",
        "values": [ "Furniture"],
        "exclude": false,
        "context": true
    }
]
Some additional rules about filters
Set Filters, Match Filters, and Relative Date Filters can’t have functions or calculations.
You can’t have multiple filters for a single field.
Parameters
When you query data sources, you can include parameters in the query request payload to override existing default parameter values. You can use parameters in:

Calculated fields: Parameters enable dynamic formulas using [Parameter Caption/Name] syntax, allowing users to create flexible calculations that respond to parameter value changes.
Ad-hoc calculations: Parameters can be referenced in temporary calculations created directly and providing a quick way to test parameter-driven logic without creating formal calculated fields.
Bins: Parameters can control bin sizes and ranges dynamically, allowing users to adjust data grouping intervals interactively without recreating bin fields.
Parameters with ad-hoc calculations
Parameters can be used within ad-hoc calculated fields to create dynamic calculations directly in the data source query. Ad-hoc calculations are temporary calculations that you create by adding a calculated field. This lets you test parameter-driven logic quickly. To use parameters in ad-hoc calculations, reference them using the syntax [Parameter Caption/Name] within your calculation expression.

For example, you can create calculations like INT([Profit] / [Profit Bin Size]) * [Profit Bin Size] directly. This approach is particularly useful for testing parameter logic, experimenting with what-if scenarios, and rapid prototyping. For more information, see Ad-Hoc Calculations.

"fields": [
	{
		"fieldCaption": "Binned Profit",
		"calculation": "INT([Profit] / [Profit Bin Size]) * [Profit Bin Size]"
	}
]
Bin with a hard-coded bin size
To query a bin on Sales with a static hard-coded bin size of 10:

"query": {
    "fields": [
        {
            "fieldCaption": "Sales",
            "function": "COUNT"
        },
       // bin size is hard coded as 10 on the published data source, no way to change it here
        {
            "fieldCaption": "Sales (bin)",
            "sortPriority": 1
        }
    ]
  }
The response:

{
    "data": [
        {
            "COUNT(Sales)": 1398,
            "Sales (bin)": 0
        },
        {
            "COUNT(Sales)": 1528,
            "Sales (bin)": 10
        },
        {
            "COUNT(Sales)": 858,
            "Sales (bin)": 20
        },
        {
            "COUNT(Sales)": 690,
            "Sales (bin)": 30
        },
        {
            "COUNT(Sales)": 492,
            "Sales (bin)": 40
        },
        {
            "COUNT(Sales)": 349,
            "Sales (bin)": 50
        },
        {
            "COUNT(Sales)": 337,
            "Sales (bin)": 60
        },
... etc. ...
    ]
}
Bin with a parameter bin size
This example queries Profit (bin). This bin has a dynamic bin size, which is a parameter. We know from our metadata request that the default value of the bin size is 200. In this example, we change the bin size to 50.

Note: Because of the rules around what Profit Bin Size can be (as seen in the metadata), It can only be between 50 and 200 with a step size of 50. Eventually we will throw an error if you try to pass in a value that is not allowed.

If you try the query without using a parameter:

"query": {
    "fields": [
        {
            "fieldCaption": "Profit",
            "function": "COUNT"
        },{
            "fieldCaption": "Profit (bin)", // default value of bin size is 200
            "sortPriority": 1
        }
    ]
  }
The response:

{
    "data": [
        {
            "COUNT(Profit)": 1,
            "Profit (bin)": -33
        },
        {
            "COUNT(Profit)": 1,
            "Profit (bin)": -20
        },
        {
            "COUNT(Profit)": 1,
            "Profit (bin)": -19
        },
        {
            "COUNT(Profit)": 1,
            "Profit (bin)": -17
        },
... etc. ...
    ]
}
The same query, but you have overridden the bin size to be a different value:

"query": {
    "fields": [
        {
            "fieldCaption": "Profit",
            "function": "COUNT"
        },{
            "fieldCaption": "Profit (bin)", // We are overriding bin size below
            "sortPriority": 1
        }
    ],
    "parameters": [
        {
            "parameterCaption": "Profit Bin Size",
            "value": 50 // Override value from 200 to 50
        }
    ]
  }
The response:

{
    "data": [
        {
            "COUNT(Profit)": 1,
            "Profit (bin)": -132
        },
        {
            "COUNT(Profit)": 1,
            "Profit (bin)": -77
        },
        {
            "COUNT(Profit)": 1,
            "Profit (bin)": -75
        },
        {
            "COUNT(Profit)": 1,
            "Profit (bin)": -68
        },
        {
            "COUNT(Profit)": 1,
            "Profit (bin)": -59
        },
... etc. ...
    ]
}
Calculated field with a parameter
This example queries a calculation that makes use of a parameter.

Edit Parameter dialog box

User Greeting edit and test area

The following query doesn’t override the parameter:

"query": {
    "fields": [
        {
            "fieldCaption": "User Greeting"
        }
    ]
}
The returns shows the default greeting:

{
    "data": [
        {
            "User Greeting": "Hello, test!"
        }
    ]
}
This next query uses a parameter to override the value of the Greeting String:

"query": {
    "fields": [
        {
            "fieldCaption": "User Greeting"
        }
    ],
    "parameters": [
        {
            "parameterCaption": "Greeting String",
            "value": "Hi" // Override default with "Hi"
        }
    ]
  }
The response shows the new value:

{
    "data": [
        {
            "User Greeting": "Hi, test!"
        }
    ]
}
Create a new bin
To make a new bin on a field, give the measure field and the bin size. VDS validates that the field you provide a bin on is a measure.

For example, this query:

"query": {
    "fields": [
        {
            "fieldCaption": "Discount", // Create a new bin on the field "Discount"
            "binSize": 0.1,
            "sortPriority": 1
        },
        {
            "fieldCaption": "Discount",
            "function": "COUNT"
        }
    ]

  }
returns:

{
    "data": [
        {
            "Discount (bin)": 0.0,
            "COUNT(Discount)": 4925
        },
        {
            "Discount (bin)": 0.1,
            "COUNT(Discount)": 148
        },
        {
            "Discount (bin)": 0.2,
            "COUNT(Discount)": 3936
        },
        {
            "Discount (bin)": 0.3,
            "COUNT(Discount)": 27
        },
... etc. ...
    ]
}
The options object
In addition to the datasource object and the query object, VDS lets you use the following additional options that can adjust the behavior of your query.

debug: (Boolean) Returns more detailed error messages from VDS in debug mode.
interpretFieldCaptionsAsFieldNames: (Boolean) When set to true, you can use the fieldName value everywhere the fieldCaption is used. This includes query fields, filter fields, fields to measure in a Top filter, parameters, table calculations, on the fly calculations, and any other place where you can pass in a fieldCaption. For example, if you set this field to true, you could query for Parameter 2 instead of Profit Bin Size.
disaggregate: (Boolean) Determines whether to aggregate results. This is the equivalent of Tableau web authoring UI. For help, see Disaggregate Data. This is only available for Query data source.
returnFormat: Whether the return format is OBJECTS (human-readable) or ARRAYS (compact).
{
"datasource": { // See above for more details
	// datasource info here
 },
"query": { // See above for more details
  "fields": [
       // Fields here
  ]
 },
"options": {
   "returnFormat": "OBJECTS",
   "debug": true,
   "disaggregate": false
}
}
Query using fieldName value
In the example of a calculation on the data source, the response shows both the fieldName and the fieldCaption:

{
    "data": [
        {
            "fieldName": "Calculation_1368249927221915648",
            "fieldCaption": "Profit Ratio",
            "dataType": "REAL",
            "defaultAggregation": "AGG",
            "columnClass": "CALCULATION",
            "formula": "SUM([Profit])/SUM([Sales])"
        }
    ]
}
If you set "interpretFieldCaptionsAsFieldNames": true,, you can use the fieldName value as the value for fieldCaption in your query. In this case, your query would use "fieldCaption":"Calculation_1368249927221915648".

Return format
VDS always returns the response body in JSON.

OBJECTS return vs. ARRAYS return option
The OBJECTS option returns field names as human-readable JSON objects. The ARRAYS option returns lists of data values.

// OBJECTS return
{
    "data": [
        {
            "Ship Mode": "Second Class",
            "SUM(Sales)": 466671.11140000017
        },
        {
            "Ship Mode": "Standard Class",
            "SUM(Sales)": 1378840.5509999855
        },
        {
            "Ship Mode": "Same Day",
            "SUM(Sales)": 129271.955
        },
        {
            "Ship Mode": "First Class",
            "SUM(Sales)": 351750.73690000066
        }
    ]
}

// ARRAYS return
{
    "data": [
        [
            "Second Class",
            466671.11140000017
        ],
        [
            "Standard Class",
            1378840.5509999855
        ],
        [
            "Same Day",
            129271.955
        ],
        [
            "First Class",
            351750.73690000066
        ]
    ]
}
Date formats
VDS does not support datetimes. You can only use dates.
VDS uses the RFC 3339 standard to input dates.
VDS outputs dates and time in the RFC 3339 standard.
VDS does not support time zones in dates.
For more information, see the VizQL Data Service API documentation.
Table Calculations Prerequisites

🕐 1 min read

This section assumes a basic understanding of table calculations, including addressing and partitioning. For more information, see the following documentation topics:

Transform Values with Table Calculations
Quick Table Calculations
Customize Table Calculations
Quick table calculations are a nice interface that matches the Quick Table Calculation dialog in Tableau. However, anything you can do with quick table calculations, you can also do with custom table calculations. Custom table calculations are the equivalent of typing in a calculation.
Table Calculations Overview

🕐 4 min read

Supported calculations
Table calculation types
Extra customizations per type
Rank table calculation options
Difference table calculation options
Moving calculation options
Custom sort calculation options
A table calculation is a transformation you apply to the values in a query. Table calculations are a special type of calculated field that computes on local data in Tableau. They are calculated based on what is currently in the query.

You can use table calculations for a variety of purposes, including:

Transforming values to rankings
Transforming values to show running totals
Transforming values to show a percent of total
Here is an example of a visualization with no table calculations.

Tableau viz with no table calculation

The equivalent VizQL Data Service (VDS) query with no table calculation applied is:

 "query": {
    "fields": [
        {
            "fieldCaption": "Region"
        },
 	 {
            "fieldCaption": "Order Date",
            "function": "YEAR"
        },{
            "fieldCaption": "Sales",
            "function": "SUM"
        },
        {
            "fieldCaption": "Profit",
            "function": "SUM"
        }
    ]
  }
For any VDS query or in the Tableau user interface, there is a virtual table that is determined by the dimensions in the query. Think of these dimensions as the ones that are “in the view” in the Tableau user interface. In the preceding example, these dimensions are YEAR(Order Date) and Region.

Supported calculations
VDS supports the following calculations:

Basic row level calculations
Aggregate calculations
Table calculations and predictive modeling calculations
Level of detail (LOD) expressions
Logical calculations (if / then / else)
String / date / number / type conversions
Parameter-based calculations
User functions
Note: The best way to ramp up on how to use table calculations in VDS is to compare the OpenAPI Schema with the Quick Table Calculations dialog in Tableau.
Each table calculation requires you to specify a field to create the table calculation from, a tableCalcType, and the dimensions to include. The dimensions you include in your query and the ordering determine the Compute Using, that is, the addressing and partitioning fields.

All table calculations must have the field on which you are operating, the table calculation type, and the list of dimensions (see more below). For each table calculation type, there could be additional requirements or customizations in accordance with the Quick Table calculations dialog.

OpenAPI basics for a table calculation field:

{
  "fieldCaption": "string",
  "tableCalculation": {
    "tableCalcType": "string",
    "dimensions": [ // Same as "Specific Dimensions" listed above      {
        "fieldCaption": "string",
      }
    ]
  }
}
Note: The dimensions field tells VDS which fields to use for partitioning and addressing in the table calculation. In other words, it tells VDS how to organize and group the data for this calculation. The table calculation is performed separately within each partition. For more information, see The basics: addressing and partitioning.
Table calculation types
The VDS OpenAPI schema allows for the following table calculation types. Depending on the type of table calculation, you will be required to provide extra fields as well, which corresponds to the various table calculation types that you would see in the Tableau UI dialog and what you would need to provide for each of those.

    "tableCalcType": {
        "type": "string",
        "enum": [
            "CUSTOM",
            "DIFFERENCE_FROM",
            "PERCENT_DIFFERENCE_FROM",
            "PERCENT_FROM",
            "PERCENT_OF_TOTAL",
            "RANK",
            "PERCENTILE",
            "RUNNING_TOTAL",
            "MOVING_CALCULATION"
        ]
Calculation Type Rank dropdown menu

We will now walk through examples of each type of table calculation.

Extra customizations per type
Different types of table calculations have advanced configuration options. You can see these in the Tableau user interface dialog as well if you’re creating Quick Table calculations.

Rank table calculation options
{
  "rankType": "COMPETITION|MODIFIED COMPETITION|DENSE|UNIQUE",
  "direction": "ASC|DESC"
}
COMPETITION: Standard ranking (1, 2, 3, 4…)
MODIFIED COMPETITION: Modified ranking (1, 2, 3, 3, 5…)
DENSE: Dense ranking (1, 2, 3, 3, 4…)
UNIQUE: Unique ranking (1, 2, 3, 4, 5…)
Difference table calculation options
{
  "relativeTo": "PREVIOUS|NEXT|FIRST|LAST",
  "levelAddress": {
    "fieldCaption": "string",
    "function": "string"
  }
}
Moving calculation options
{
  "aggregation": "SUM|AVG|MIN|MAX",
  "previous": -2, // number of periods before current
  "next": 0, // number of periods after current
  "includeCurrent": true, // include current period
  "fillInNull": false // fill null values
}
Custom sort calculation options
Additionally, many table calculation types allow for a custom sort. You can define another field in the query to sort on.
Custome Sort dialog

{
  "customSort": {
    "fieldCaption": "string",
    "function": "string",
    "direction": "ASC|DESC"
  }
}
Table Calculation Query Examples

🕐 5 min read

Example 1: Rank profit by region and year
Example 2: Percent of total profit by region and year
Example 3: Running total profit by region and year
Example 4: Difference from previous year’s profit
Example 5: Moving average profit (three-year window)
Secondary table calculations
Order of operations
Supported combinations
Use cases
Common patterns
Example: Running total with percent difference secondary calculation
Example 1: Rank profit by region and year
This example ranks profit values within each region-year combination.

"query": {
    "fields": [
      {
        "fieldCaption": "Region"
      },
      {
        "fieldCaption": "Order Date",
        "function": "YEAR"
      },
      {
        "fieldCaption": "Sales",
        "function": "SUM"
      },
      {
        "fieldCaption": "Profit",
        "function": "SUM"
      },
      {
        "fieldCaption": "Profit",
        "function": "SUM",
        "tableCalculation": {
          "tableCalcType": "RANK",
          "dimensions": [
            {
              "fieldCaption": "Region"
            },
            {
              "fieldCaption": "Order Date",
              "function": "YEAR"
            }
          ],
           "rankType": "COMPETITION"
        }
      }
    ]
  }
In the response, each region-year combination will have profit values ranked from highest to lowest.

Example 2: Percent of total profit by region and year
This example shows what percentage each profit value represents of the total profit for that region-year.

  "query": {
    "fields": [
      {
        "fieldCaption": "Region"
      },
      {
        "fieldCaption": "Order Date",
        "function": "YEAR"
      },
      {
        "fieldCaption": "Sales",
        "function": "SUM"
      },
      {
        "fieldCaption": "Profit",
        "function": "SUM"
      },
      {
        "fieldCaption": "Profit",
        "function": "SUM",
        "tableCalculation": {
          "tableCalcType": "PERCENT_OF_TOTAL",
          "dimensions": [
            {
              "fieldCaption": "Region"
            },
            {
              "fieldCaption": "Order Date",
              "function": "YEAR"
            }
          ]
        }
      }
    ]
  }
In the response, each profit value will be shown as a percentage of the total profit for that specific region and year.

Example 3: Running total profit by region and year
This example shows cumulative profit over time for each region.

"query": {
    "fields": [
        {
            "fieldCaption": "Region"
        },
        {
            "fieldCaption": "Order Date",
            "function": "YEAR"
        },
        {
            "fieldCaption": "Sales",
            "function": "SUM"
        },
        {
            "fieldCaption": "Profit",
            "function": "SUM"
        },
        {
            "fieldCaption": "Profit",
            "function": "SUM",
            "tableCalculation": {
                "tableCalcType": "RUNNING_TOTAL",
                "dimensions": [
                    {
                        "fieldCaption": "Region"
                    },
                    {
                        "fieldCaption": "Order Date",
                        "function": "YEAR"
                    }
                ],
                "restartEvery": {
                    "fieldCaption": "Order Date",
                    "function": "YEAR"
                }
            }
        }
    ]
}
Example 4: Difference from previous year’s profit
This example shows how much profit changed compared to the previous year.

"query": {
  "fields": [
    {
      "fieldCaption": "Region"
    },
    {
      "fieldCaption": "Order Date",
      "function": "YEAR"
    },
    {
      "fieldCaption": "Sales",
      "function": "SUM"
    },
    {
      "fieldCaption": "Profit",
      "function": "SUM"
    },
    {
      "fieldCaption": "Profit",
      "function": "SUM",
      "tableCalculation": {
        "tableCalcType": "DIFFERENCE_FROM",
        "dimensions": [
          {
            "fieldCaption": "Order Date",
            "function": "YEAR"
          }
        ],
        "relativeTo": "PREVIOUS"
      }
    }
  ]
}
The response shows the absolute difference in profit compared to the previous year for each region.

Example 5: Moving average profit (three-year window)
This example shows a three-year moving average of profit for each region.


  "query": {
    "fields": [
      {
        "fieldCaption": "Region"
      },
      {
        "fieldCaption": "Order Date",
        "function": "YEAR"
      },
      {
        "fieldCaption": "Sales",
        "function": "SUM"
      },
      {
        "fieldCaption": "Profit",
        "function": "SUM"
      },
      {
        "fieldCaption": "Profit",
        "function": "SUM",
        "tableCalculation": {
          "tableCalcType": "MOVING_CALCULATION",
          "dimensions": [
            {
              "fieldCaption": "Region"
            },
            {
              "fieldCaption": "Order Date",
              "function": "YEAR"
            }
          ],
          "aggregation": "SUM",
          "previous": -2,
          "next": 1,
          "includeCurrent": true
        }
      }
    ]
  }
Secondary table calculations
There is an option to add secondary table calculations.

Order of operations
Primary calculation is applied first
Secondary calculation is applied to the results of the primary calculation
Supported combinations
RUNNING_TOTAL can have any secondary calculation
MOVING_CALCULATION can have any secondary calculation
Other table calculation types do not support secondary calculations
Use cases
Smoothing: Apply moving average to running totals for trend analysis
Ranking: Rank the results of running totals or moving averages
Normalization: Convert running totals to percentages or percentiles
Growth Analysis: Show growth rates of cumulative values
Common patterns
Running Total + Percent of Total: Show cumulative contribution to total
Moving Average + Rank: Rank smoothed values
Running Total + Difference: Show growth of cumulative values
Moving Average + Percentile: Show relative position of smoothed values
Example: Running total with percent difference secondary calculation
This example shows how to first calculate running totals, then show the percentage change in running totals.

  "query": {
    "fields": [
      {
        "fieldCaption": "Region"
      },
      {
        "fieldCaption": "Order Date",
        "function": "YEAR"
      },
      {
        "fieldCaption": "Sales",
        "function": "SUM"
      },
      {
        "fieldCaption": "Profit",
        "function": "SUM"
      },
      {
        "fieldCaption": "Profit",
         "function": "SUM",
        "tableCalculation": {
          "tableCalcType": "RUNNING_TOTAL",
          "dimensions": [
            {
              "fieldCaption": "Region"
            },
            {
              "fieldCaption": "Order Date",
              "function": "YEAR"
            }
          ],
          "aggregation": "SUM",
          "secondaryTableCalculation": {
            "tableCalcType": "PERCENT_DIFFERENCE_FROM",
            "dimensions": [
              {
                "fieldCaption": "Region"
              },
              {
                "fieldCaption": "Order Date",
                "function": "YEAR"
              }
            ],
            "relativeTo": "PREVIOUS"
          }
        }
      }
    ]
  }
Custom Table Calculations

🕐 3 min read

Common custom table calculation patterns
Difference from previous
Percent change
Year-over-year growth
Running total
Moving average
Custom table calculations allow you to write your own Tableau calculation formulas using the CUSTOM table calculation type. This provides the flexibility to create complex calculations that go beyond the standard quick table calculations available in Tableau Desktop.
For more information, see the Tableau documentation for:

Customize Table Calculations
Table Calculation Functions
Write a table calculation in the “calculation” field of the Table Calculation Field and give it a name.

For example:

"query": {
    "fields": [
        {
            "fieldCaption": "Region",
            "sortPriority": 1
        },{
              "fieldCaption": "Segment",
              "sortPriority": 2
        }, {
              "fieldCaption": "Order Date",
              "function": "YEAR",
              "sortPriority": 3
        }, {
            "fieldCaption": "MyDifferenceCalc",
            "calculation": "ZN(SUM([Sales])) - LOOKUP(ZN(SUM([Sales])), -1)",
            "tableCalculation": {
                "tableCalcType": "CUSTOM",
                "dimensions": [
                    {
                        "fieldCaption": "Region"
                    }, {
                        "fieldCaption": "Segment"
                    }, {
                        "fieldCaption": "Order Date",
                        "function": "YEAR"
                    }
                ]
            }
        }
    ]
  }
The preceding example does the following:

ZN(SUM([Sales])): Gets the current row’s sales value (ZN handles nulls).
LOOKUP(ZN(SUM([Sales])), \-1): Gets the previous row’s sales value.
-: Subtracts the previous value from the current value.
The result shows the difference in sales from the previous period.

Common custom table calculation patterns
Difference from previous
This example calculates the absolute difference from the previous value, using the formula, ZN(SUM(\[Sales\])) - LOOKUP(ZN(SUM(\[Sales\])), -1).

{
  "fieldCaption": "Sales Difference",
  "calculation": "ZN(SUM([Sales])) - LOOKUP(ZN(SUM([Sales])), -1)",
  "tableCalculation": {
    "tableCalcType": "CUSTOM",
    "dimensions": [
      {
        "fieldCaption": "Region"
      },
      {
        "fieldCaption": "Order Date",
        "function": "YEAR"
      }
    ]
  }
}
Percent change
This example calculates the percentage change from the previous value, using the formula: (ZN(SUM([Sales])) - LOOKUP(ZN(SUM([Sales])), -1)) / LOOKUP(ZN(SUM([Sales])), -1).

{
  "fieldCaption": "Sales % Change",
  "calculation": "(ZN(SUM([Sales])) - LOOKUP(ZN(SUM([Sales])), -1)) / LOOKUP(ZN(SUM([Sales])), -1)",
  "tableCalculation": {
    "tableCalcType": "CUSTOM",
    "dimensions": [
      {
        "fieldCaption": "Region"
      },
      {
        "fieldCaption": "Order Date",
        "function": "YEAR"
      }
    ]
  }
}
Year-over-year growth
This example calculates year-over-year growth, using the formula, SUM([Sales]) - LOOKUP(SUM([Sales]), -4)) / LOOKUP(SUM([Sales]), -4).

{
  "fieldCaption": "YoY Growth",
  "calculation": "(SUM([Sales]) - LOOKUP(SUM([Sales]), -4)) / LOOKUP(SUM([Sales]), -4)",
  "tableCalculation": {
    "tableCalcType": "CUSTOM",
    "dimensions": [
      {
        "fieldCaption": "Region"
      },
      {
        "fieldCaption": "Order Date",
        "function": "YEAR"
      }
    ]
  }
}
Running total
This example calculates cumulative totals, using the formulat, RUNNING_SUM(SUM([Sales])).

{
  "fieldCaption": "Running Total Sales",
  "calculation": "RUNNING_SUM(SUM([Sales]))",
  "tableCalculation": {
    "tableCalcType": "CUSTOM",
    "dimensions": [
      {
        "fieldCaption": "Region"
      },
      {
        "fieldCaption": "Order Date",
        "function": "YEAR"
      }
    ]
  }
}
Moving average
This example calculates a three-period moving average, using the formula, WINDOW\_AVG(SUM(\[Sales\]), \-2, 0\).

{
  "fieldCaption": "Moving Average Sales",
  "calculation": "WINDOW_AVG(SUM([Sales]), -2, 0)",
  "tableCalculation": {
    "tableCalcType": "CUSTOM",
    "dimensions": [
      {
        "fieldCaption": "Region"
      },
      {
        "fieldCaption": "Order Date",
        "function": "YEAR"
      }
    ]
  }
}
Nested Table Calculations

🕐 2 min read

VDS supports nested table calculations. If you have one table calculation within another one, you can set the dimensions for compute Using independently for each table calculation referenced. To configure nested calculations independently, use:

tableCalcType": "NESTED"
For example, if you have three calculations saved on your published data source:

1-nest, with the formula TOTAL(SUM([Sales])) (a table calc)
2-nest, with the formula TOTAL(SUM([Profit]))(also a table calc)
3-nest, with the formula [1-nest] + [2-nest] (not a table calc in itself, but has two nested table calculations)
Our goal is to query the calculation 1-nest. In this case, you want to compute the dimensions of 1-nest and 2-nest independently. You could do this with the following query:

 "query": {
   "fields": [
     {
       "fieldCaption": "Region",
       "sortPriority": 1
     },
     {
       "fieldCaption": "Segment",
       "sortPriority": 2
     },
     {
       "fieldCaption": "Order Date",
       "function": "YEAR",
       "sortPriority": 3
     },
     {
       "fieldCaption": "3-nest",
       "tableCalculation": {
         "tableCalcType": "CUSTOM",
         "dimensions": [
         ]
       },
       "nestedTableCalculations": [
         {
           "fieldCaption": "1-nest",
           "tableCalcType": "NESTED",
           "dimensions": [
             {
               "fieldCaption": "Region"
             },
             {
               "fieldCaption": "Segment"
             },
             {
               "fieldCaption": "Order Date",
               "function": "YEAR"
             }
           ]
         },
         {
           "fieldCaption": "2-nest",
           "tableCalcType": "NESTED",
           "dimensions": [
             {
               "fieldCaption": "Region"
             },
             {
               "fieldCaption": "Segment"
             }
           ],
           "restartEvery": {
             "fieldCaption": "Region"
           }
         }
       ]
     }
   ]
 }

Because 1-nest isn’t a table calculation in itself, the dimensions list is empty.

Let’s say you want to query another calculation saved on your published data source, called 4-nest. You intend to use the formula WINDOW_SUM(SUM([SALES]), -2, 0) - [2-nest].

Because 4-nest is a table calculation in itself (WINDOW_SUM), but so is 2-nest,. You can add dimensions for Compute Using for each calculation.

 "query": {
    "fields": [
      {
        "fieldCaption": "Region",
        "sortPriority": 1
      },
      {
        "fieldCaption": "Segment",
        "sortPriority": 2
      },
      {
        "fieldCaption": "Order Date",
        "function": "YEAR",
        "sortPriority": 3
      },
      {
        "fieldCaption": "4-nest",
        "tableCalculation": {
          "tableCalcType": "CUSTOM",
          "dimensions": [
            {
              "fieldCaption": "Region"
            },
            {
              "fieldCaption": "Segment"
            },
            {
              "fieldCaption": "Order Date",
              "function": "YEAR"
            }
          ]
        },
        "nestedTableCalculations": [
          {
            "fieldCaption": "2-nest",
            "tableCalcType": "NESTED",
            "dimensions": [
              {
                "fieldCaption": "Region"
              },
              {
                "fieldCaption": "Segment"
              }
            ]
          }
        ]
      }
    ]
  }
  Error Codes

🕐 2 min read

HTTP Status	Error Code	Condition	Details
400	400000	Bad request	The content of the request body is invalid. Check for missing or incomplete JSON.
400	400802	Invalid API request	The incoming request isn’t valid per the OpenAPI specification.
400	400803	Validation failed	The incoming request isn’t valid per the validation rules.
400	400800	Invalid formula for calculation	Invalid custom calculation syntax. For help, see Formatting Calculations in Tableau.
400	400804	Response too large	The response value exceeds the limit. You must apply a filter in your request.
401	401001	Log-in error	The log-in failed for the given user.
401	401002	Invalid authorization credentials	The provided auth token is formatted incorrectly.
403	403157	Feature disabled	The feature is disabled.
403	403800	API access permission denied	The user doesn’t have API Access granted on the given data source. Set the API Access capability for the given data source to Allowed. For help, see Permission Capabilities and Templates.
404	404934	Unknown field	The requested field doesn’t exist.
404	404935	Duplicate field caption	There are two or more fields with the same caption in the published data source.
404	404950	API endpoint not found	The request endpoint doesn’t exist.
408	408000	Request timeout	The request timed out.
409	409000	User already on site	HTTP status conflict.
429	429000	Too many requests	Too many requests in the allotted amount of time. For help, see Licensing and data transfer.
500	500000	Internal server error	The request could not be completed.
500	500810	VizQL Data Service (VDS) empty table response	The underlying data engine returned empty data value response.
500	500811	VDS missing table	The underlying data engine returned empty metadata associated with response.
500	500812	Error while processing an error	Internal processing error.
500	500813	Parameter name undefined	There’s an invalid parameter in the data source and VDS can’t find what type parameter it is.
500	500814	Bin name undefined	There’s an invalid bin in the data source and VDS can’t find what the bin type is.
500	500815	Data source model undefined	VDS can’t find information about the data model.
501	501000	Not implemented	Can’t find response from upstream server.
503	503800	VDS unavailable	The underlying data engine is unavailable.
503	503801	VDS discovery error	The upstream service can’t be found.
504	504000	Gateway timeout	The upstream service response timed out.
Limitations
🕐 1 min read
Calculations
Data sources
Fields
Filters
Licensing and data transfer
Queries
Response size
Other
Calculations
VizQL Data Service (VDS) doesn’t support these calculation types:
Spatial calculations
Python or R calculations (like SCRIPT_REAL)
Tableau Analytics Extensions calculations
Pass-through calculations (like RAWSQL)
Fiscal date calculations
COUNT(table)
Calculations on features we don’t support:
Sets
Combined fields
Also, you can’t reference a group in a calculation.
Data sources
VDS doesn’t support cube data sources.
Fields
VDS doesn’t support querying for sets and combined fields. These field types are not returned as part of the Request data source metadata method.
Filters
VDS doesn’t support bins or groups in filters.
Set filters, match filters, and relative date filters can’t have functions or calculations.
The field property of a filter can contain a fieldName, or a fieldName and a function, for example Sales, or SUM of Sales. Within a query, you can only have one filter per field. So if you have a filter on SUM of Sales, you can’t add another filter in the same query for SUM of Sales. However, you can add a filter for Sales because it’s a different field.
Licensing and data transfer
VDS is available for all license models. There’s a cap on usage determined by the number of Tableau Creator licenses assigned to a site. Each Creator license on a site raises the cap for the entire site by 100 queries per hour.
Queries
VDS doesn’t support all features of Tableau services. For a full list of supported features, see Create a Query.
Response size
VDS has a response size limit of 1 GB. Any response size larger than that results in an error. To avoid such an error, we recommend that you apply a filter to the data to limit the response size.
Other
VDS doesn’t support date-time aggregations (for example, HOUR, MINUTE, etc.).
Troubleshooting
🕐 2 min read
Make sure your URL is correct by hitting the simple-request endpoint. If you see “ahoy” returned, you know you can reach the service.
Turn on the debug flag in options to get a more detailed error message.
  {
   "datasource": {
     "datasourceLuid": ""
   },
   "options": {
     "debug": true
   }
  }
For Tableau Server, examine the log files. For help, see Tableau Server Logs and Log File Locations.
To debug log in issues, see Testing and Troubleshooting REST API Calls.
A common error is the following:
  {"errorCode":"400000",
  "message":"Unable to parse the request 
  body. Please ensure it is formatted as 
  valid JSON. (Illegal unquoted 
  character ((CTRL-CHAR, code 10)): has 
  to be escaped using backslash to be 
  included in string value)."}
This likely means that you have an extra indentation after your datasource-luid. Make sure the data source LUID is a single line.