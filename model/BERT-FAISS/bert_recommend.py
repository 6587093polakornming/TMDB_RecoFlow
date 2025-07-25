# -*- coding: utf-8 -*-
"""bert_recommend

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1dc319y1afn_qJJtUvcL4YgJNlgM3oJuJ

# Recommendation Movie Using Bert Model
"""

!pip install -q sentence-transformers faiss-cpu tqdm

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
from tqdm import tqdm
from sklearn.model_selection import train_test_split

"""## Step 1: Load movie metadata, user profiles, and ratings"""

# Assuming you have the data files available
try:
    movie_df = pd.read_parquet('cbf_movie.parquet') # Using parquet as in your original notebook
    user_profile_df = pd.read_csv('user_last_genres.csv')
    ratings_df = pd.read_parquet('user_ratings_200users_30each_int.parquet') # Using parquet as in your original notebook
except FileNotFoundError:
    print("Make sure 'cbf_movie.parquet', 'user_last_genres.csv', and 'user_ratings_200users_30each.parquet' are in the correct directory.")

movie_df.head()

user_profile_df.head()

ratings_df.head()

"""## Step 2: Prepare movie text for embedding"""

# Handle potential missing values in relevant columns
movie_df.dropna(subset=['title', 'overview', 'genres'], inplace=True)

# Combine features into a single text column
movie_df['text'] = movie_df['title'] + '. ' + movie_df['overview'].fillna('') + ' Genres: ' + movie_df['genres'].fillna('')

# Select only necessary columns
movie_df = movie_df[['movie_id', 'text']]

display(movie_df.head())

"""## Step 3: Generate BERT embeddings for movie descriptions"""

# Load a pre-trained BERT model
model = SentenceTransformer('all-MiniLM-L6-v2')
model = model.to('cuda')  # Moves model to GPU

batch_size = 64
movie_texts = movie_df['text'].tolist()
movie_ids = movie_df['movie_id'].tolist()

all_embeddings = []
for i in tqdm(range(0, len(movie_texts), batch_size)):
    batch_texts = movie_texts[i:i+batch_size]
    batch_embeds = model.encode(batch_texts, device="cuda")
    all_embeddings.append(batch_embeds)

all_embeddings = np.vstack(all_embeddings).astype('float32')

# Create a dictionary mapping movie_id to its embedding
movie_embed_dict = dict(zip(movie_ids, all_embeddings))

print(f"Generated embeddings for {len(movie_embed_dict)} movies.")

# np.save("movie_embeddings.npy", all_embeddings)
all_embeddings = np.load("movie_embeddings.npy")

"""## Step 4: Generate user embeddings from last genres"""

user_embeddings = {}
for _, row in user_profile_df.iterrows():
    user_id = row['user_id']
    genres = ', '.join([str(row[col]) for col in row.index if col.startswith('Last_genres')])
    text = f"User's last watched genres: {genres}"
    user_embeddings[user_id] = model.encode(text, device="cuda")

# print(f"Number of users embedded: {len(user_embeddings)}")

"""## Step 5: Index movie embeddings using FAISS"""

index = faiss.IndexFlatL2(all_embeddings.shape[1])
index.add(all_embeddings)

"""## Step 6: Prepare train/test data for evaluation"""

# ratings_df['relevant'] = (ratings_df['rating'] >= 1.0).astype(int)
# ratings_df = ratings_df[ratings_df['relevant'] == 1]

# train_rows, test_rows = [], []
# for uid, group in ratings_df.groupby("user_id"):
#     if len(group) >= 5:
#         train, test = train_test_split(group, test_size=0.2, random_state=42)
#         train_rows.append(train)
#         test_rows.append(test)

# train_df = pd.concat(train_rows)
# test_df = pd.concat(test_rows)

ratings_df['relevant'] = (ratings_df['rating'] >= 0.0).astype(int)
test_df = ratings_df[ratings_df['relevant'] == 1]

"""## Step 7: Evaluate Precision@5 and Recall@5"""

def evaluate(user_id, k=5):
    if user_id not in user_embeddings:
        return 0, 0
    user_vec = np.expand_dims(user_embeddings[user_id], axis=0).astype('float32')
    D, I = index.search(user_vec, k)
    recommended = [movie_ids[i] for i in I[0]]
    actual = test_df[test_df['user_id'] == user_id]['movie_id'].tolist()
    hits = len(set(recommended) & set(actual))
    precision = hits / k
    recall = hits / len(actual) if actual else 0
    return precision, recall

results = [evaluate(uid, k=5) for uid in test_df['user_id'].unique()]
avg_precision = np.mean([r[0] for r in results])
avg_recall = np.mean([r[1] for r in results])

print(f"Precision@5: {avg_precision:.4f}")
print(f"Recall@5: {avg_recall:.4f}")

results = [evaluate(uid, k=10) for uid in test_df['user_id'].unique()]
avg_precision = np.mean([r[0] for r in results])
avg_recall = np.mean([r[1] for r in results])

print(f"Precision@10: {avg_precision:.4f}")
print(f"Recall@10: {avg_recall:.4f}")

def recommend_movies(user_id, top_k=10):
    if user_id not in user_embeddings:
        print(f"User ID {user_id} not found in user_embeddings.")
        return

    # Get user vector and search similar movies
    user_vec = np.expand_dims(user_embeddings[user_id], axis=0).astype('float32')
    D, I = index.search(user_vec, top_k)

    print(f"\nTop {top_k} recommended movies for user {user_id}:\n")
    results = []

    for i, movie_idx in enumerate(I[0]):
        movie_id = movie_ids[movie_idx]
        similarity_score = 1 / (1 + D[0][i])  # Convert L2 distance to pseudo-similarity
        movie_info = movie_df[movie_df['movie_id'] == movie_id].iloc[0]

        results.append({
            "Rank": i + 1,
            "Movie ID": movie_id,
            "Title": movie_info['text'].split('.')[0],
            "Genres": movie_info['text'].split('Genres: ')[-1],
            "Score": round(similarity_score, 4)
        })

    return pd.DataFrame(results)

recommendation_df = recommend_movies(1, top_k=10)
recommendation_df

