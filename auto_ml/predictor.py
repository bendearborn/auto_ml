from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

import utils

from sklearn.grid_search import GridSearchCV


class Predictor(object):


    def __init__(self, type_of_algo, column_descriptions, verbose=True):
        self.type_of_algo = type_of_algo
        self.column_descriptions = column_descriptions
        self.verbose = verbose
        self.trained_pipeline = None

        # figure out which column has a value 'output'
        output_column = [key for key, value in column_descriptions.items() if value.lower() == 'output'][0]
        self.output_column = output_column


    def _construct_pipeline(self, user_input_func=None, ml_for_analytics=False, model_name='LogisticRegression', optimize_final_model=False):

        pipeline_list = []
        if user_input_func is not None:
            pipeline_list.append(('user_func', FunctionTransformer(func=user_input_func, pass_y=False, validate=False) ))

        pipeline_list.append(('basic_transform', utils.BasicDataCleaning()))
        pipeline_list.append(('dv', DictVectorizer(sparse=True)))
        # We have to include ml_for_analytics here to tell that stage to save the feature ranges.
        # TODO(PRESTON): refactor to do this inside _construct_pipeline_search_params instead
        pipeline_list.append(('final_model', utils.FinalModelATC(model_name=model_name, perform_grid_search_on_model=optimize_final_model)))

        constructed_pipeline = Pipeline(pipeline_list)
        return constructed_pipeline


    def _construct_pipeline_search_params(self, optimize_entire_pipeline=True, optimize_final_model=False, ml_for_analytics=False):

        gs_params = {}

        if optimize_final_model:
            gs_params['final_model__perform_grid_search_on_model'] = [True, False]

        if ml_for_analytics:
            gs_params['final_model__ml_for_analytics'] = [True]

        else:
            if optimize_entire_pipeline:
                gs_params['final_model__model_name'] = ['RandomForestClassifier', 'LogisticRegression']

        return gs_params


    def train(self, raw_training_data, user_input_func=None, optimize_entire_pipeline=False, optimize_final_model=False, print_analytics_output=False):

        # split out out output column so we have a proper X, y dataset
        output_splitter = utils.SplitOutput(self.output_column)
        X, y = output_splitter.transform(raw_training_data)

        ppl = self._construct_pipeline(user_input_func, optimize_final_model)

        self.gs_params = self._construct_pipeline_search_params(optimize_entire_pipeline=optimize_entire_pipeline, optimize_final_model=optimize_final_model)

        # We will be performing GridSearchCV every time, even if the space we are searching over is null
        gs = GridSearchCV(
            # Fit on the pipeline.
            ppl,
            self.grid_search_params,
            # Train across all cores.
            n_jobs=-1,
            # Be verbose (lots of printing).
            verbose=10,
            # Print warnings when we fail to fit a given combination of parameters, but do not raise an error.
            error_score=10,
            # TODO(PRESTON): change scoring to be RMSE by default
            scoring=None
        )

        gs.fit(X, y)

        self.trained_pipeline = gs.best_estimator_

        return self



    def ml_for_analytics(self, raw_training_data, user_input_func=None, optimize_entire_pipeline=False, optimize_final_model=False, print_analytics_output=False):

        # split out out output column so we have a proper X, y dataset
        output_splitter = utils.SplitOutput(self.output_column)
        X, y = output_splitter.transform(raw_training_data)

        ppl = self._construct_pipeline(user_input_func, optimize_final_model=optimize_final_model, ml_for_analytics=True)

        for model_name in ['LogisticRegression', 'RandomForestClassifier']:

            self.grid_search_params = self._construct_pipeline_search_params(optimize_entire_pipeline=optimize_entire_pipeline, optimize_final_model=optimize_final_model, ml_for_analytics=True)

            self.grid_search_params['final_model__model_name'] = [model_name]

            gs = GridSearchCV(
                # Fit on the pipeline.
                ppl,
                self.grid_search_params,
                # Train across all cores.
                n_jobs=-1,
                # Be verbose (lots of printing).
                verbose=10,
                # Print warnings when we fail to fit a given combination of parameters, but do not raise an error.
                error_score=10,
                # TODO(PRESTON): change scoring to be RMSE by default
                scoring=None
            )

            gs.fit(X, y)
            self.trained_pipeline = gs.best_estimator_

            if model_name in ('LogisticRegression', 'Ridge'):
                self._print_ml_analytics_results_regression()
            elif model_name == 'RandomForestClassifier':
                self._print_ml_analytics_results_random_forest()

    def _print_ml_analytics_results_random_forest(self):

        trained_feature_names = self.trained_pipeline.named_steps['dv'].get_feature_names()

        trained_feature_importances = self.trained_pipeline.named_steps['final_model'].model.feature_importances_

        feature_infos = zip(trained_feature_names, trained_feature_importances)

        sorted_feature_infos = sorted(feature_infos, key=lambda x: x[1])

        for feature in sorted_feature_infos[:50]:
            print(feature[0] + ': ' + str(round(feature[1], 4)))


    def _print_ml_analytics_results_regression(self):

        trained_feature_names = self.trained_pipeline.named_steps['dv'].get_feature_names()

        trained_coefficients = self.trained_pipeline.named_steps['final_model'].model.coef_[0]

        feature_ranges = self.trained_pipeline.named_steps['final_model'].feature_ranges

        # TODO(PRESTON): readability. Can probably do this in a single zip statement.
        feature_summary = []
        for col_idx, feature_name in enumerate(trained_feature_names):

            potential_impact = feature_ranges[col_idx] * trained_coefficients[col_idx]
            summary_tuple = (feature_name, trained_coefficients[col_idx], potential_impact)
            feature_summary.append(summary_tuple)

        sorted_feature_summary = sorted(feature_summary, key=lambda x: abs(x[2]))

        print('The following is a list of feature names and their coefficients. This is followed by calculating a reasonable range for each feature, and multiplying by that feature\'s coefficient, to get an idea of the scale of the possible impact from this feature.')
        print('This printed list will only contain the top 50 features.')
        for summary in sorted_feature_summary[:50]:
            print(summary[0] + ': ' + str(round(summary[1], 4)))
            print('The potential impact of this feature is: ' + str(round(summary[2], 4)))

        # TODO(PRESTON)
        # Figure out how to access the FinalModelATC from our pipeline
        # Figure out how to access the model from FinalModelATC
        # Figure out how to get the coefficients from the best regression and random forest
        # Figure out how to get that particular model's features from DictVectorizer (we will be doing a lot of feature engineering and feature selection in very near term versions of this repo)
            # Might have to wrap DictVectorizer in a class that writes the results to the pipeline object or something?
        # consider letting them pass this in as a flag for train. would probably be much easier to calculate these things if we know to beforehand
        # look into putting some logic into FinalModelATC that keeps the best model/parameters around in an easy way for analytics.
        # Figure out the reasonable range for whatever features we do have left, for regression printing


    def print_training_summary(self):
        pass
        # Print some nice summary output of all the training we did.
        # maybe allow the user to pass in a flag to write info to a file


    def predict(self, prediction_data):

        return self.trained_pipeline.predict(prediction_data)

    def predict_proba(self, prediction_data):

        return self.trained_pipeline.predict_proba(prediction_data)


    def score(self, X_test, y_test):
        return self.trained_pipeline.score(X_test, y_test)

