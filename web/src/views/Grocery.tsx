import { useState } from "react";
import type { FormEvent } from "react";

import { ConfirmDelete, Field, Modal } from "../components/Modal";
import { ViewFrame } from "../components/ViewFrame";
import { ApiError, api } from "../lib/api";
import { useToast } from "../lib/context";
import { t } from "../lib/i18n";
import { useResource } from "../lib/useResource";
import type { MealIdea, Recipe } from "../lib/types";

export function Grocery() {
  const toast = useToast();
  const shopping = useResource(() => api.shopping());
  const recipes = useResource(() => api.recipes());
  const mealIdeas = useResource(() => api.mealIdeas());
  const [text, setText] = useState("");
  const [qty, setQty] = useState("");
  const [ideaSearch, setIdeaSearch] = useState("");
  const [ideaCategory, setIdeaCategory] = useState("");
  const [editingRecipe, setEditingRecipe] = useState<Recipe | null | "new">(null);
  const [pendingRecipe, setPendingRecipe] = useState<Recipe | null>(null);
  const [editingMealIdea, setEditingMealIdea] = useState<MealIdea | null | "new">(null);
  const [pendingMealIdea, setPendingMealIdea] = useState<MealIdea | null>(null);

  const items = shopping.data ?? [];
  const bought = items.filter((item) => item.done).length;
  const allMealIdeas = mealIdeas.data ?? [];
  const ideaCategories = [...new Set(allMealIdeas.map((idea) => idea.category))];
  const ideas = allMealIdeas.filter((idea) => {
    const query = ideaSearch.trim().toLowerCase();
    const matchesSearch = !query || `${idea.category} ${idea.name} ${idea.status}`.toLowerCase().includes(query);
    return matchesSearch && (!ideaCategory || idea.category === ideaCategory);
  });

  const add = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    setText("");
    setQty("");
    await api.addShopping({ text: trimmed, quantity: qty.trim() || null });
    shopping.reload();
  };

  return (
    <ViewFrame
      title={t("grocery_title")}
      subtitle={t("grocery_sub")}
      resources={[shopping, recipes, mealIdeas]}
    >
      <div className="grocery-grid">
        <section className="card grocery-shopping-card">
          <h2>🛒 {t("shopping_heading", { done: bought, total: items.length })}</h2>
          <form className="shop-add grocery-add" onSubmit={add}>
            <input
              type="text"
              maxLength={200}
              placeholder={t("shopping_placeholder")}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <input
              className="grocery-quantity"
              type="text"
              maxLength={100}
              placeholder={t("quantity")}
              value={qty}
              onChange={(e) => setQty(e.target.value)}
            />
            <button type="submit" className="btn">{t("add_btn")}</button>
          </form>

          {items.length === 0 && <div className="empty-note">{t("no_shopping")}</div>}
          {items.map((item) => (
            <div className={`todo-item ${item.done ? "done" : ""}`} key={item.id}>
              <input
                type="checkbox"
                checked={item.done}
                aria-label={item.text}
                onChange={async (e) => {
                  const done = e.target.checked;
                  shopping.patch((rows) =>
                    rows.map((row) => (row.id === item.id ? { ...row, done } : row)),
                  );
                  try {
                    await api.patchShopping(item.id, { done });
                  } finally {
                    shopping.reload();
                  }
                }}
              />
              <div className="todo-body"><div className="todo-title">{item.text}</div></div>
              {item.quantity && <span className="freq-tag">{item.quantity}</span>}
              <button
                type="button"
                className="btn danger icon"
                aria-label={t("delete")}
                onClick={async () => {
                  await api.deleteShopping(item.id);
                  shopping.reload();
                }}
              >
                ×
              </button>
            </div>
          ))}

          {items.length > 0 && (
            <div className="btn-row grocery-clear-actions">
              <button
                type="button"
                className="btn subtle small"
                onClick={async () => {
                  await api.clearShopping(true);
                  toast(t("deleted"));
                  shopping.reload();
                }}
              >
                {t("clear_bought", { n: bought })}
              </button>
              <button
                type="button"
                className="btn danger small"
                onClick={async () => {
                  await api.clearShopping(false);
                  toast(t("deleted"));
                  shopping.reload();
                }}
              >
                {t("clear_all")}
              </button>
            </div>
          )}
        </section>

        <section className="card grocery-recipes-card">
          <h2>📖 {t("recipes_heading", { n: (recipes.data ?? []).length })}</h2>
          <button type="button" className="btn grocery-new-recipe" onClick={() => setEditingRecipe("new")}>
            {t("new_recipe")}
          </button>
          {(recipes.data ?? []).length === 0 && <div className="empty-note">{t("no_recipes")}</div>}
          <div className="grocery-recipe-list">
            {(recipes.data ?? []).map((recipe) => (
              <article
                className="recipe-card"
                key={recipe.id}
                tabIndex={0}
                role="button"
                onClick={() => setEditingRecipe(recipe)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") setEditingRecipe(recipe);
                }}
              >
                <div className="recipe-name">{recipe.name}</div>
                {recipe.ingredients && <div className="recipe-preview">{recipe.ingredients}</div>}
                {recipe.video_url && (
                  <a
                    href={recipe.video_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    ▶ {t("video_link")}
                  </a>
                )}
              </article>
            ))}
          </div>
        </section>
      </div>

      <section className="card meal-ideas-card">
        <div className="meal-ideas-head">
          <h2>{t("menu_ideas_heading", { n: allMealIdeas.length })}</h2>
          <button type="button" className="btn" onClick={() => setEditingMealIdea("new")}>
            {t("new_meal_idea")}
          </button>
        </div>
        <div className="meal-ideas-tools">
          <input
            className="meal-ideas-search"
            type="search"
            value={ideaSearch}
            placeholder={t("search")}
            onChange={(e) => setIdeaSearch(e.target.value)}
          />
          <select
            className="meal-ideas-category-filter"
            aria-label={t("meal_category")}
            value={ideaCategory}
            onChange={(e) => setIdeaCategory(e.target.value)}
          >
            <option value="">{t("all_categories")}</option>
            {ideaCategories.map((category) => <option key={category} value={category}>{category}</option>)}
          </select>
        </div>
        <div className="meal-ideas-table" role="table">
          <div className="meal-ideas-row meal-ideas-table-head" role="row">
            <span role="columnheader">{t("meal_category")}</span>
            <span role="columnheader">{t("meal_name")}</span>
            <span role="columnheader">{t("meal_status")}</span>
            <span role="columnheader" />
          </div>
          {ideas.map((idea) => (
            <div className="meal-ideas-row" role="row" key={idea.id}>
              <span role="cell">{idea.category}</span>
              <span role="cell">{idea.name}</span>
              <span className="muted" role="cell">{idea.status}</span>
              <button
                type="button"
                className="meal-idea-edit"
                aria-label={t("edit")}
                onClick={() => setEditingMealIdea(idea)}
              >
                ✎
              </button>
            </div>
          ))}
          {ideas.length === 0 && <div className="empty-note">{t("no_match")}</div>}
        </div>
      </section>

      {editingRecipe && (
        <RecipeModal
          recipe={editingRecipe === "new" ? null : editingRecipe}
          onClose={() => setEditingRecipe(null)}
          onAddToShopping={async (ingredients) => {
            const entries = ingredients
              .split("\n")
              .map((line) => line.trim().replace(/^[•*-]\s*/, ""))
              .filter(Boolean);
            // One request at a time keeps a long ingredient list reliable on a hosted
            // instance that may throttle a burst of concurrent writes.
            for (const entry of entries) await api.addShopping({ text: entry, quantity: null });
            shopping.reload();
            toast(t("ingredients_added_to_shopping", { n: entries.length }));
          }}
          {...(editingRecipe === "new"
            ? {}
            : {
                onDelete: () => {
                  setEditingRecipe(null);
                  setPendingRecipe(editingRecipe);
                },
              })}
          onSaved={() => {
            setEditingRecipe(null);
            toast(t("saved"));
            recipes.reload();
          }}
        />
      )}
      {pendingRecipe && (
        <ConfirmDelete
          what={pendingRecipe.name}
          onCancel={() => setPendingRecipe(null)}
          onConfirm={async () => {
            await api.deleteRecipe(pendingRecipe.id);
            setPendingRecipe(null);
            setEditingRecipe(null);
            toast(t("deleted"));
            recipes.reload();
          }}
        />
      )}
      {editingMealIdea && (
        <MealIdeaModal
          idea={editingMealIdea === "new" ? null : editingMealIdea}
          onClose={() => setEditingMealIdea(null)}
          {...(editingMealIdea === "new"
            ? {}
            : {
                onDelete: () => {
                  setEditingMealIdea(null);
                  setPendingMealIdea(editingMealIdea);
                },
              })}
          onSaved={() => {
            setEditingMealIdea(null);
            toast(t("saved"));
            mealIdeas.reload();
          }}
        />
      )}
      {pendingMealIdea && (
        <ConfirmDelete
          what={pendingMealIdea.name}
          onCancel={() => setPendingMealIdea(null)}
          onConfirm={async () => {
            await api.deleteMealIdea(pendingMealIdea.id);
            setPendingMealIdea(null);
            setEditingMealIdea(null);
            toast(t("deleted"));
            mealIdeas.reload();
          }}
        />
      )}
    </ViewFrame>
  );
}

function RecipeModal({
  recipe,
  onClose,
  onAddToShopping,
  onDelete,
  onSaved,
}: {
  recipe: Recipe | null;
  onClose: () => void;
  onAddToShopping: (ingredients: string) => Promise<void>;
  onDelete?: () => void;
  onSaved: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [addingIngredients, setAddingIngredients] = useState(false);
  const [ingredients, setIngredients] = useState(recipe?.ingredients ?? "");
  return (
    <Modal title={recipe ? `${t("edit")} — ${recipe.name}` : t("new_recipe")} onClose={onClose} busy={busy} actionsLeading={
      <>
        {onDelete && <button type="button" className="btn danger" onClick={onDelete}>{t("delete")}</button>}
        <button
          type="button"
          className="btn ghost"
          disabled={!ingredients.trim() || busy || addingIngredients}
          onClick={async () => {
            setAddingIngredients(true);
            try {
              await onAddToShopping(ingredients);
            } catch (err) {
              setError(err instanceof ApiError ? err.detail : t("save_failed"));
            } finally {
              setAddingIngredients(false);
            }
          }}
        >
          {t("add_ingredients_to_shopping")}
        </button>
      </>
    } onSubmit={async (form) => {
      setBusy(true);
      setError(null);
      const payload = {
        name: String(form.get("name") ?? ""),
        ingredients: String(form.get("ingredients") ?? "") || null,
        steps: String(form.get("steps") ?? "") || null,
        temp: String(form.get("temp") ?? "") || null,
        video_url: String(form.get("video_url") ?? "") || null,
      };
      try {
        if (recipe) await api.replaceRecipe(recipe.id, payload);
        else await api.createRecipe(payload);
        onSaved();
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : t("save_failed"));
      } finally {
        setBusy(false);
      }
    }}>
      {error && <p className="auth-error">{error}</p>}
      <Field label={t("recipe_name")}><input name="name" required maxLength={200} defaultValue={recipe?.name ?? ""} /></Field>
      <Field label={t("recipe_ingredients_help")}><textarea name="ingredients" rows={5} maxLength={2000} placeholder={"雞胸肉 300g\n醬油 2 大匙\n蒜末 3 瓣"} value={ingredients} onChange={(e) => setIngredients(e.target.value)} /></Field>
      <Field label={t("cooking_method")}><textarea name="steps" rows={5} maxLength={4000} placeholder={"1. 醃 20 分鐘\n2. 氣炸鍋 180°C 15 分鐘, 翻面再 5 分鐘"} defaultValue={recipe?.steps ?? ""} /></Field>
      <Field label={t("heat")}><input name="temp" maxLength={100} placeholder="例如: 180°C / 中小火" defaultValue={recipe?.temp ?? ""} /></Field>
      <Field label={t("video_url")}><input name="video_url" type="url" maxLength={500} placeholder="例如: https://www.youtube.com/watch?v=..." defaultValue={recipe?.video_url ?? ""} /></Field>
    </Modal>
  );
}

function MealIdeaModal({
  idea,
  onClose,
  onDelete,
  onSaved,
}: {
  idea: MealIdea | null;
  onClose: () => void;
  onDelete?: () => void;
  onSaved: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal title={idea ? `${t("edit")} — ${idea.name}` : t("new_meal_idea_title")} onClose={onClose} busy={busy} onSubmit={async (form) => {
      setBusy(true);
      setError(null);
      const payload = {
        category: String(form.get("category") ?? ""),
        name: String(form.get("name") ?? ""),
        status: String(form.get("status") ?? ""),
      };
      try {
        if (idea) await api.replaceMealIdea(idea.id, payload);
        else await api.createMealIdea(payload);
        onSaved();
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : t("save_failed"));
      } finally {
        setBusy(false);
      }
    }}>
      {error && <p className="auth-error">{error}</p>}
      <Field label={t("meal_category")}><input name="category" required maxLength={100} placeholder="例如: Chicken、Beef、Vegetable" defaultValue={idea?.category ?? ""} /></Field>
      <Field label={t("meal_name")}><input name="name" required maxLength={200} placeholder="輸入菜名" defaultValue={idea?.name ?? ""} /></Field>
      <Field label={t("meal_status")}><input name="status" required maxLength={50} placeholder="例如: 想試、常做" defaultValue={idea?.status ?? "常做"} /></Field>
      {onDelete && <button type="button" className="btn danger" onClick={onDelete}>{t("delete")}</button>}
    </Modal>
  );
}
