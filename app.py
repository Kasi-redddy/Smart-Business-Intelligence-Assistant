import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Setting up the main page configuration
st.set_page_config(
    page_title="Smart Business Intelligence Assistant", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Helper function to clean up messy column names - you know how Excel files can be
def sanitize_column_headers(dataframe):
    """Clean up those pesky column names that come from Excel"""
    cleaned_headers = []
    for header in dataframe.columns:
        # Remove weird characters and normalize spacing
        clean_header = re.sub(r'[^\w\s]', '_', str(header).strip())
        clean_header = re.sub(r'\s+', '_', clean_header.lower())
        # Handle duplicate names by adding numbers
        counter = 1
        original_header = clean_header
        while clean_header in cleaned_headers:
            clean_header = f"{original_header}_{counter}"
            counter += 1
        cleaned_headers.append(clean_header)
    
    dataframe.columns = cleaned_headers
    return dataframe

def process_uploaded_data(raw_dataframe):
    """Do some basic cleanup on the data - convert objects to strings, handle nulls"""
    processed_df = raw_dataframe.copy()
    
    # Convert object columns to strings for consistency
    for column_name in processed_df.columns:
        if processed_df[column_name].dtype == 'object':
            processed_df[column_name] = processed_df[column_name].astype(str)
            # Clean up those annoying 'nan' strings
            processed_df[column_name] = processed_df[column_name].replace('nan', np.nan)
    
    return processed_df

def figure_out_column_types(dataframe):
    """Smart detection of what kind of data we're dealing with"""
    column_categories = {}
    
    for col in dataframe.columns:
        # Try to see if it's numeric first
        numeric_attempt = pd.to_numeric(dataframe[col], errors='coerce')
        non_null_count = numeric_attempt.dropna().shape[0]
        
        if non_null_count > 0 and non_null_count / len(dataframe) > 0.5:
            # Looks like numbers to me
            if dataframe[col].dtype in ['int64', 'float64'] or numeric_attempt.dtype in ['int64', 'float64']:
                column_categories[col] = 'numerical'
            else:
                column_categories[col] = 'numerical'
        else:
            # Check if it might be dates
            try:
                date_attempt = pd.to_datetime(dataframe[col], errors='coerce')
                if date_attempt.dropna().shape[0] > len(dataframe) * 0.3:
                    column_categories[col] = 'datetime'
                    continue
            except:
                pass
            
            # Count unique values to decide if it's categorical
            unique_vals = dataframe[col].nunique(dropna=True)
            total_rows = len(dataframe)
            
            if unique_vals == 2:
                column_categories[col] = 'binary'
            elif unique_vals <= 20 or unique_vals / total_rows < 0.1:
                column_categories[col] = 'categorical'
            else:
                column_categories[col] = 'text'
    
    return column_categories

def smart_column_finder(search_term, available_columns):
    """Find the best matching column for a user's query"""
    search_normalized = search_term.lower().replace(" ", "").replace("_", "")
    
    # First try exact matches
    for col in available_columns:
        col_normalized = col.lower().replace("_", "").replace(" ", "")
        if search_normalized == col_normalized:
            return col
    
    # Then try partial matches
    for col in available_columns:
        col_normalized = col.lower().replace("_", "").replace(" ", "")
        if search_normalized in col_normalized or col_normalized in search_normalized:
            return col
    
    # Finally try word-by-word matching
    search_words = search_term.lower().split()
    for word in search_words:
        for col in available_columns:
            if word in col.lower():
                return col
    
    return None

def hunt_for_categorical_values(query_text, dataframe, col_types):
    """Look for specific values mentioned in the query"""
    for column_name, data_type in col_types.items():
        if data_type in ["categorical", "binary"]:
            unique_values = dataframe[column_name].dropna().unique()
            for value in unique_values:
                if str(value).lower() in query_text.lower():
                    return column_name, str(value)
    return None, None

def add_calculated_columns(dataframe):
    """Add some useful calculated fields if we can"""
    # If we have birth year, calculate age
    birth_year_cols = [col for col in dataframe.columns if 'birth' in col.lower() and 'year' in col.lower()]
    if birth_year_cols and 'age' not in dataframe.columns:
        birth_col = birth_year_cols[0]
        current_year = datetime.now().year
        dataframe['age'] = current_year - pd.to_numeric(dataframe[birth_col], errors='coerce')
    
    # Add more calculated fields as needed
    return dataframe

def parse_natural_language_query(user_question, dataframe, column_types):
    """The heart of our system - figure out what the user wants"""
    query_lower = user_question.lower()
    
    # Chart requests
    if any(phrase in query_lower for phrase in ["pie chart", "pie graph"]):
        target_col = smart_column_finder(
            query_lower.replace("pie chart", "").replace("pie graph", "").replace("of", "").strip(), 
            dataframe.columns
        )
        if not target_col:
            # Default to first categorical column
            categorical_cols = [c for c, t in column_types.items() if t == "categorical"]
            target_col = categorical_cols[0] if categorical_cols else None
        return ("create_pie_chart", target_col)
    
    if any(phrase in query_lower for phrase in ["bar chart", "bar graph", "show bars"]):
        target_col = smart_column_finder(
            query_lower.replace("bar chart", "").replace("bar graph", "").replace("show bars", "").replace("of", "").strip(),
            dataframe.columns
        )
        if not target_col:
            categorical_cols = [c for c, t in column_types.items() if t == "categorical"]
            target_col = categorical_cols[0] if categorical_cols else None
        return ("create_bar_chart", target_col)
    
    if any(phrase in query_lower for phrase in ["histogram", "distribution", "spread"]):
        target_col = smart_column_finder(
            query_lower.replace("histogram", "").replace("distribution", "").replace("spread", "").replace("of", "").strip(),
            dataframe.columns
        )
        if not target_col:
            numeric_cols = [c for c, t in column_types.items() if t == "numerical"]
            target_col = numeric_cols[0] if numeric_cols else None
        return ("create_histogram", target_col)
    
    if any(phrase in query_lower for phrase in ["line chart", "trend", "over time"]):
        # Look for time-based and value columns
        time_col = None
        value_col = None
        
        for col in dataframe.columns:
            if any(time_word in col.lower() for time_word in ["date", "year", "month", "time"]):
                time_col = col
                break
        
        remaining_query = query_lower.replace("line chart", "").replace("trend", "").replace("over time", "")
        value_col = smart_column_finder(remaining_query.strip(), dataframe.columns)
        
        return ("create_line_chart", time_col, value_col)
    
    if any(phrase in query_lower for phrase in ["scatter", "correlation plot", "relationship"]):
        # Look for two numeric columns
        words = query_lower.replace("scatter", "").replace("plot", "").replace("correlation", "").split(" vs ")
        if len(words) == 2:
            col1 = smart_column_finder(words[0].strip(), dataframe.columns)
            col2 = smart_column_finder(words[1].strip(), dataframe.columns)
        else:
            numeric_columns = [c for c, t in column_types.items() if t == "numerical"]
            col1 = numeric_columns[0] if len(numeric_columns) > 0 else None
            col2 = numeric_columns[1] if len(numeric_columns) > 1 else None
        return ("create_scatter_plot", col1, col2)
    
    # Statistical queries
    if any(phrase in query_lower for phrase in ["average", "mean"]):
        target_col = smart_column_finder(
            query_lower.replace("average", "").replace("mean", "").replace("what is", "").replace("the", "").strip(),
            dataframe.columns
        )
        if not target_col:
            numeric_cols = [c for c, t in column_types.items() if t == "numerical"]
            target_col = numeric_cols[0] if numeric_cols else None
        return ("calculate_statistic", target_col, "mean")
    
    if any(phrase in query_lower for phrase in ["total", "sum"]):
        target_col = smart_column_finder(
            query_lower.replace("total", "").replace("sum", "").replace("what is", "").replace("the", "").strip(),
            dataframe.columns
        )
        if not target_col:
            numeric_cols = [c for c, t in column_types.items() if t == "numerical"]
            target_col = numeric_cols[0] if numeric_cols else None
        return ("calculate_statistic", target_col, "sum")
    
    if any(phrase in query_lower for phrase in ["maximum", "max", "highest"]):
        target_col = smart_column_finder(
            query_lower.replace("maximum", "").replace("max", "").replace("highest", "").replace("what is", "").replace("the", "").strip(),
            dataframe.columns
        )
        if not target_col:
            numeric_cols = [c for c, t in column_types.items() if t == "numerical"]
            target_col = numeric_cols[0] if numeric_cols else None
        return ("calculate_statistic", target_col, "max")
    
    if any(phrase in query_lower for phrase in ["minimum", "min", "lowest"]):
        target_col = smart_column_finder(
            query_lower.replace("minimum", "").replace("min", "").replace("lowest", "").replace("what is", "").replace("the", "").strip(),
            dataframe.columns
        )
        if not target_col:
            numeric_cols = [c for c, t in column_types.items() if t == "numerical"]
            target_col = numeric_cols[0] if numeric_cols else None
        return ("calculate_statistic", target_col, "min")
    
    if "median" in query_lower:
        target_col = smart_column_finder(
            query_lower.replace("median", "").replace("what is", "").replace("the", "").strip(),
            dataframe.columns
        )
        if not target_col:
            numeric_cols = [c for c, t in column_types.items() if t == "numerical"]
            target_col = numeric_cols[0] if numeric_cols else None
        return ("calculate_statistic", target_col, "median")
    
    # Filtering and counting queries
    if any(phrase in query_lower for phrase in ["how many", "count"]):
        # Look for numeric filters first
        under_match = re.search(r'under (\d+)', query_lower)
        above_match = re.search(r'above (\d+)', query_lower)
        
        if under_match:
            threshold = float(under_match.group(1))
            target_col = smart_column_finder(query_lower, dataframe.columns)
            if not target_col:
                numeric_cols = [c for c, t in column_types.items() if t == "numerical"]
                target_col = numeric_cols[0] if numeric_cols else None
            return ("filter_and_count", target_col, "<", threshold)
        
        if above_match:
            threshold = float(above_match.group(1))
            target_col = smart_column_finder(query_lower, dataframe.columns)
            if not target_col:
                numeric_cols = [c for c, t in column_types.items() if t == "numerical"]
                target_col = numeric_cols[0] if numeric_cols else None
            return ("filter_and_count", target_col, ">", threshold)
        
        # Look for categorical filters
        category_col, category_val = hunt_for_categorical_values(query_lower, dataframe, column_types)
        if category_col and category_val:
            return ("filter_count_category", category_col, category_val)
        
        # Just count all rows
        return ("count_all_rows",)
    
    # Grouping and comparison queries
    if any(phrase in query_lower for phrase in ["compare", "group by", "breakdown", "by category"]):
        group_column = smart_column_finder(query_lower, dataframe.columns)
        value_column = None
        
        # Look for a numeric column mentioned
        for col, col_type in column_types.items():
            if col_type == "numerical" and col.lower() in query_lower:
                value_column = col
                break
        
        return ("group_and_analyze", group_column, value_column)
    
    # Summary requests
    if any(phrase in query_lower for phrase in ["summary", "describe", "overview", "statistics"]):
        return ("generate_summary",)
    
    # Default fallback
    return ("generate_summary",)

def execute_analysis_request(action_info, dataframe):
    """Execute the parsed query and return results"""
    action_type = action_info[0]
    
    try:
        if action_type == "calculate_statistic":
            column_name, stat_type = action_info[1], action_info[2]
            if not column_name:
                return "I couldn't identify which column to analyze.", None, None
            
            numeric_data = pd.to_numeric(dataframe[column_name], errors='coerce')
            
            if stat_type == "mean":
                result = numeric_data.mean()
                return f"The average value in '{column_name}' is {result:.2f}", None, None
            elif stat_type == "sum":
                result = numeric_data.sum()
                return f"The total sum of '{column_name}' is {result:.0f}", None, None
            elif stat_type == "max":
                result = numeric_data.max()
                return f"The maximum value in '{column_name}' is {result:.2f}", None, None
            elif stat_type == "min":
                result = numeric_data.min()
                return f"The minimum value in '{column_name}' is {result:.2f}", None, None
            elif stat_type == "median":
                result = numeric_data.median()
                return f"The median value in '{column_name}' is {result:.2f}", None, None
        
        elif action_type == "filter_and_count":
            column_name, operator, threshold = action_info[1], action_info[2], action_info[3]
            if not column_name:
                return "I couldn't identify which column to filter on.", None, None
            
            numeric_data = pd.to_numeric(dataframe[column_name], errors='coerce')
            
            if operator == "<":
                filtered_count = numeric_data[numeric_data < threshold].shape[0]
                return f"There are {filtered_count} records where '{column_name}' is under {threshold}", None, None
            elif operator == ">":
                filtered_count = numeric_data[numeric_data > threshold].shape[0]
                return f"There are {filtered_count} records where '{column_name}' is above {threshold}", None, None
        
        elif action_type == "filter_count_category":
            column_name, target_value = action_info[1], action_info[2]
            matching_rows = dataframe[dataframe[column_name].str.lower() == target_value.lower()].shape[0]
            return f"There are {matching_rows} records where '{column_name}' equals '{target_value}'", None, None
        
        elif action_type == "count_all_rows":
            total_rows = dataframe.shape[0]
            return f"Your dataset contains {total_rows} total records", None, None
        
        elif action_type == "group_and_analyze":
            group_col, value_col = action_info[1], action_info[2]
            if not group_col:
                return "I couldn't determine which column to group by.", None, None
            
            if value_col:
                # Group by category and calculate mean of numeric column
                grouped_data = dataframe.groupby(group_col)[value_col].apply(
                    lambda x: pd.to_numeric(x, errors='coerce').mean()
                ).reset_index()
                grouped_data.columns = [group_col, f"average_{value_col}"]
                return f"Average '{value_col}' grouped by '{group_col}':", grouped_data, None
            else:
                # Just count occurrences
                count_data = dataframe[group_col].value_counts().reset_index()
                count_data.columns = [group_col, "count"]
                return f"Count breakdown by '{group_col}':", count_data, None
        
        elif action_type == "create_bar_chart":
            column_name = action_info[1]
            if not column_name:
                return "I couldn't determine which column to chart.", None, None
            
            value_counts = dataframe[column_name].value_counts()
            
            # Create interactive plotly chart
            fig = px.bar(
                x=value_counts.index, 
                y=value_counts.values,
                title=f"Distribution of {column_name.replace('_', ' ').title()}",
                labels={'x': column_name.replace('_', ' ').title(), 'y': 'Count'}
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            return f"Bar chart showing the distribution of '{column_name}'", None, fig
        
        elif action_type == "create_histogram":
            column_name = action_info[1]
            if not column_name:
                return "I couldn't determine which column to analyze.", None, None
            
            numeric_data = pd.to_numeric(dataframe[column_name], errors='coerce').dropna()
            
            fig = px.histogram(
                x=numeric_data, 
                nbins=25,
                title=f"Distribution of {column_name.replace('_', ' ').title()}"
            )
            fig.update_layout(
                xaxis_title=column_name.replace('_', ' ').title(),
                yaxis_title='Frequency'
            )
            st.plotly_chart(fig, use_container_width=True)
            return f"Histogram showing the distribution of '{column_name}'", None, fig
        
        elif action_type == "create_pie_chart":
            column_name = action_info[1]
            if not column_name:
                return "I couldn't determine which column to chart.", None, None
            
            value_counts = dataframe[column_name].value_counts()
            
            fig = px.pie(
                values=value_counts.values, 
                names=value_counts.index,
                title=f"Composition of {column_name.replace('_', ' ').title()}"
            )
            st.plotly_chart(fig, use_container_width=True)
            return f"Pie chart showing the composition of '{column_name}'", None, fig
        
        elif action_type == "create_line_chart":
            time_col, value_col = action_info[1], action_info[2]
            if not time_col or not value_col:
                return "I need both a time column and a value column for a line chart.", None, None
            
            # Try to parse dates
            try:
                dates = pd.to_datetime(dataframe[time_col], errors='coerce')
                values = pd.to_numeric(dataframe[value_col], errors='coerce')
                
                fig = px.line(
                    x=dates, 
                    y=values,
                    title=f"{value_col.replace('_', ' ').title()} Over Time"
                )
                fig.update_layout(
                    xaxis_title=time_col.replace('_', ' ').title(),
                    yaxis_title=value_col.replace('_', ' ').title()
                )
                st.plotly_chart(fig, use_container_width=True)
                return f"Line chart showing '{value_col}' over '{time_col}'", None, fig
            except:
                return "I had trouble creating the line chart with those columns.", None, None
        
        elif action_type == "create_scatter_plot":
            col1, col2 = action_info[1], action_info[2]
            if not col1 or not col2:
                return "I need two numeric columns for a scatter plot.", None, None
            
            x_data = pd.to_numeric(dataframe[col1], errors='coerce')
            y_data = pd.to_numeric(dataframe[col2], errors='coerce')
            
            fig = px.scatter(
                x=x_data, 
                y=y_data,
                title=f"Relationship between {col1.replace('_', ' ').title()} and {col2.replace('_', ' ').title()}"
            )
            fig.update_layout(
                xaxis_title=col1.replace('_', ' ').title(),
                yaxis_title=col2.replace('_', ' ').title()
            )
            st.plotly_chart(fig, use_container_width=True)
            return f"Scatter plot showing the relationship between '{col1}' and '{col2}'", None, fig
        
        elif action_type == "generate_summary":
            summary_stats = dataframe.describe(include='all')
            return "Here's a comprehensive summary of your dataset:", summary_stats, None
        
        else:
            return "I'm not sure how to handle that request yet.", None, None
    
    except Exception as error:
        return f"I encountered an error while processing your request: {str(error)}", None, None

# --- Main Streamlit Application ---

st.title("Smart Business Intelligence Assistant")
st.markdown("""
Welcome to your personal data analyst! Upload any Excel or CSV file and ask questions in plain English. 
I'll help you uncover insights, create visualizations, and understand your data better.
""")

# File upload section
uploaded_data_file = st.file_uploader(
    "Upload your data file", 
    type=["xlsx", "xls", "csv"],
    help="Supports Excel (.xlsx, .xls) and CSV files"
)

if uploaded_data_file is not None:
    try:
        # Determine file type and read accordingly
        file_extension = uploaded_data_file.name.split('.')[-1].lower()
        
        if file_extension == 'csv':
            raw_dataframe = pd.read_csv(uploaded_data_file)
        else:
            raw_dataframe = pd.read_excel(uploaded_data_file)
        
        # Process the data
        clean_dataframe = sanitize_column_headers(raw_dataframe)
        clean_dataframe = add_calculated_columns(clean_dataframe)
        processed_dataframe = process_uploaded_data(clean_dataframe)
        detected_column_types = figure_out_column_types(processed_dataframe)
        
        st.success(f"Successfully loaded your file! Found {len(processed_dataframe)} rows and {len(processed_dataframe.columns)} columns.")
        
        # Create two columns for layout
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader(" Ask me anything about your data")
            user_question = st.text_input(
                "Type your question here...", 
                placeholder="e.g., 'Show me a bar chart of sales by region' or 'What's the average age?'"
            )
            
            if user_question:
                with st.spinner("Analyzing your question..."):
                    # Parse and execute the query
                    parsed_action = parse_natural_language_query(user_question, processed_dataframe, detected_column_types)
                    response_text, result_table, chart_figure = execute_analysis_request(parsed_action, processed_dataframe)
                    
                    # Display the response
                    st.markdown(f"** Analysis Result:** {response_text}")
                    
                    if result_table is not None:
                        st.dataframe(result_table, use_container_width=True)
        
        with col2:
            st.subheader(" Dataset Overview")
            st.metric("Total Rows", len(processed_dataframe))
            st.metric("Total Columns", len(processed_dataframe.columns))
            
            # Show column types
            with st.expander("Column Information"):
                for col, col_type in detected_column_types.items():
                    st.write(f"**{col}**: {col_type}")
        
        # Data preview section
        with st.expander(" Preview Your Data"):
            st.dataframe(processed_dataframe.head(10), use_container_width=True)
        
        # Quick insights section
        st.subheader(" Quick Insights")
        insight_cols = st.columns(3)
        
        with insight_cols[0]:
            if st.button(" Show Summary Statistics"):
                summary_action = ("generate_summary",)
                summary_response, summary_table, _ = execute_analysis_request(summary_action, processed_dataframe)
                st.write(summary_response)
                if summary_table is not None:
                    st.dataframe(summary_table)
        
        with insight_cols[1]:
            numeric_columns = [col for col, col_type in detected_column_types.items() if col_type == "numerical"]
            if numeric_columns and st.button(" Quick Bar Chart"):
                categorical_cols = [col for col, col_type in detected_column_types.items() if col_type == "categorical"]
                if categorical_cols:
                    chart_action = ("create_bar_chart", categorical_cols[0])
                    execute_analysis_request(chart_action, processed_dataframe)
        
        with insight_cols[2]:
            if st.button(" Data Types Overview"):
                type_counts = {}
                for col_type in detected_column_types.values():
                    type_counts[col_type] = type_counts.get(col_type, 0) + 1
                
                st.write("**Column Type Distribution:**")
                for data_type, count in type_counts.items():
                    st.write(f"• {data_type.title()}: {count} columns")
    
    except Exception as processing_error:
        st.error(f" Oops! I had trouble processing your file: {str(processing_error)}")
        st.info("Please make sure your file is a valid Excel or CSV file with proper formatting.")

else:
    st.info(" Please upload an Excel (.xlsx) or CSV file to get started!")
    
    # Show some example queries
    st.subheader(" Example Questions You Can Ask")
    example_questions = [
        "What's the average income by department?",
        "Show me a pie chart of customer segments",
        "How many employees are under 30?",
        "Create a histogram of sales amounts",
        "Compare performance by region",
        "What's the maximum salary?",
        "Show me a scatter plot of age vs income"
    ]
    
    for question in example_questions:
        st.write(f"• {question}")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        Built with ❤️ by kasi for NeoStats AI Engineer Assessment | 
        Powered by advanced natural language processing
    </div>
    """, 
    unsafe_allow_html=True
)